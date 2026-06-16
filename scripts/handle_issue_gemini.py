import os
import sys
import json
import base64
import subprocess as sp
from pathlib import Path
from google import genai
from google.genai import types

# Extract the base64-encoded arguments from sys.argv
try:
    repo = base64.b64decode(sys.argv[1]).decode('utf-8').strip()
    num = base64.b64decode(sys.argv[2]).decode('utf-8').strip()
    title = base64.b64decode(sys.argv[3]).decode('utf-8').strip()
    body = base64.b64decode(sys.argv[4]).decode('utf-8').strip()
except Exception as e:
    print(f"Error decoding base64 arguments: {e}")
    sys.exit(1)

# --- UPDATED PATHS FOR NATIVE LINUX PARTITION ---
branch = f'gemini/issue-{num}'
base_dir = Path('/home/deb/Github Linux/n8n-CodeRunner')
repo_dir = Path('/home/deb/Github Linux/n8n-CodeRunner-action-repo')

# --- READ API KEYS & TOKENS ---
key_path = base_dir / '/api_keys/gemini_api_key.md'
token_path = base_dir / 'github_token.md'

try:
    gemini_key = key_path.read_text(encoding='utf-8').strip()
    gh_token = token_path.read_text(encoding='utf-8').strip()
    client = genai.Client(api_key=gemini_key)
except FileNotFoundError as e:
    print(f"Error: Missing configuration file: {e.filename}")
    sys.exit(1)
except Exception as e:
    print(f"Error reading access credentials: {e}")
    sys.exit(1)

# --- GIT INITIALIZATION & AUTHENTICATION ---
if not repo_dir.exists():
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    authenticated_url = f"https://x-access-token:{gh_token}@github.com/{repo}.git"
    sp.run(['git', 'clone', authenticated_url, str(repo_dir)], check=True)

os.chdir(repo_dir)

# Standard git checkout sequence
sp.run(['git', 'checkout', 'main'], check=True)
sp.run(['git', 'pull'], check=True)
sp.run(['git', '-c', 'advice.detachedHead=false', 'checkout', '-B', branch], check=True)

# --- READ EXISTING CODEBASE CONTEXT ---
codebase_context = ""
exclude_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.venv'}
allowed_extensions = {'.py', '.js', '.json', '.html', '.css', '.md', '.txt'}

for path in repo_dir.rglob('*'):
    if path.is_file() and not any(part in path.parts for part in exclude_dirs):
        if path.suffix in allowed_extensions:
            try:
                relative_path = path.relative_to(repo_dir)
                codebase_context += f"\n--- FILE: {relative_path} ---\n"
                codebase_context += path.read_text(encoding='utf-8')
            except Exception:
                pass 

# --- GEMINI RUN GENERATION ---
prompt = f"""
You are an automated code fixer. Fix the following repository issue based on the provided codebase context.

Issue #{num}: {title}
Description: {body}

--- CURRENT CODEBASE CONTEXT ---
{codebase_context}
--------------------------------

Analyze the issue and modify or create the necessary files. 
You must output a structured list containing the relative filepaths and their complete rewritten contents.
"""

json_schema = types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "filepath": types.Schema(type=types.Type.STRING, description="The relative path to the file inside the repo."),
            "content": types.Schema(type=types.Type.STRING, description="The absolute new/modified full content for this file.")
        },
        required=["filepath", "content"]
    )
)

config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=json_schema,
    temperature=0.1
)

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=prompt,
    config=config
)

# Parse and apply file edits
try:
    file_changes = json.loads(response.text)
    if not file_changes:
        print("Gemini analyzed the repository and found no changes required.")
        sys.exit(0)
        
    for change in file_changes:
        target_file = repo_dir / change['filepath']
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(change['content'], encoding='utf-8')
        print(f"Successfully updated: {change['filepath']}")
        
except Exception as e:
    print(f"Failed to automatically apply Gemini's edits. Error: {e}")
    sys.exit(1)

# --- COMMIT, PUSH AND CREATE PULL REQUEST ---
env_with_auth = {**os.environ, "GH_TOKEN": gh_token, "GITHUB_TOKEN": gh_token}

sp.run(['git', 'add', '.'], check=True)
sp.run(['git', 'commit', '-m', f'Fix issue #{num} via Gemini API'], check=True)

# Force push using the authenticated URL explicitly to override old remote profiles
authenticated_remote = f"https://x-access-token:{gh_token}@github.com/{repo}.git"
sp.run(['git', 'push', authenticated_remote, f'{branch}:refs/heads/{branch}', '--force'], check=True, env=env_with_auth)

# Create a Pull Request via GitHub CLI
sp.run([
    'gh', 'pr', 'create',
    '--title', f'Fix issue #{num}: {title}',
    '--body', f'Closes #{num}. Automated fix by Gemini API.',
    '--base', 'main',
    '--head', branch
], check=True, env=env_with_auth)

print(f"🚀 Success! Gemini processed Issue #{num} and opened a new Pull Request on branch {branch}.")