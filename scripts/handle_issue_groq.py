import os
import sys
import json
import base64
import subprocess as sp
from pathlib import Path
from groq import Groq
from pydantic import BaseModel, Field
from typing import List

# Extract the base64-encoded arguments from sys.argv
try:
    repo = base64.b64decode(sys.argv[1]).decode('utf-8').strip()
    num = base64.b64decode(sys.argv[2]).decode('utf-8').strip()
    title = base64.b64decode(sys.argv[3]).decode('utf-8').strip()
    body = base64.b64decode(sys.argv[4]).decode('utf-8').strip()
except Exception as e:
    print(f"Error decoding base64 arguments: {e}")
    sys.exit(1)

# --- DYNAMIC PATH RESOLUTION ---
branch = f'groq/issue-{num}'
script_dir = Path(__file__).resolve().parent
base_dir = script_dir.parent  # Points directly to the root n8n-CodeRunner folder
repo_dir = base_dir.parent / 'n8n-CodeRunner-action-repo'

# --- READ API KEYS & TOKENS ---
key_path = base_dir / '/api_keys/groq_api_key.md'
token_path = base_dir / 'github_token.md'

try:
    groq_key = key_path.read_text(encoding='utf-8').strip()
    gh_token = token_path.read_text(encoding='utf-8').strip()
    client = Groq(api_key=groq_key)
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

# --- GROQ STRUCTURED OUTPUT SCHEMA ---
class FileEdit(BaseModel):
    filepath: str = Field(description="The relative path to the file inside the repo.")
    content: str = Field(description="The absolute new/modified full content for this file.")

class CodebaseChanges(BaseModel):
    changes: List[FileEdit]


# --- GROQ API RUN GENERATION ---
prompt = f"""
You are an automated code fixer. Fix the following repository issue based on the provided codebase context.

Issue #{num}: {title}
Description: {body}

--- CURRENT CODEBASE CONTEXT ---
{codebase_context if codebase_context else "[The repository is currently empty. You must create any necessary files to resolve the issue.]"}
--------------------------------

Analyze the issue and modify or create the necessary files.
"""

try:
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior software engineer. Fix the repository issues by generating code edits.\n\n"
                    "CRITICAL: You must return a JSON object containing a list of changes. Even if the repository is empty "
                    "or files do not exist, you must create them. Do not return an empty list.\n\n"
                    "Your response must follow this exact JSON format:\n"
                    "{\n"
                    '  "changes": [\n'
                    "    {\n"
                    '      "filepath": "README.md",\n'
                    '      "content": "# My App\\nhello world"\n'
                    "    }\n"
                    "  ]\n"
                    "}"
                )
            },
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    
    # Parse the verified JSON payload directly
    response_data = json.loads(chat_completion.choices[0].message.content)
    file_changes = response_data.get("changes", [])
    
except Exception as e:
    print(f"Failed during Groq API inference sequence. Error: {e}")
    sys.exit(1)

# Apply file edits
if not file_changes:
    print("Groq analyzed the repository and found no changes required.")
    sys.exit(0)
    
for change in file_changes:
    target_file = repo_dir / change['filepath']
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(change['content'], encoding='utf-8')
    print(f"Successfully updated: {change['filepath']}")

# --- COMMIT, PUSH AND CREATE PULL REQUEST ---
env_with_auth = {**os.environ, "GH_TOKEN": gh_token, "GITHUB_TOKEN": gh_token}

sp.run(['git', 'add', '.'], check=True)
sp.run(['git', 'commit', '-m', f'Fix issue #{num} via Groq API'], check=True)

authenticated_remote = f"https://x-access-token:{gh_token}@github.com/{repo}.git"
sp.run(['git', 'push', authenticated_remote, f'{branch}:refs/heads/{branch}', '--force'], check=True, env=env_with_auth)

sp.run([
    'gh', 'pr', 'create',
    '--title', f'Fix issue #{num}: {title}',
    '--body', f'Closes #{num}. Automated fix by Groq Llama-3 API.',
    '--base', 'main',
    '--head', branch
], check=True, env=env_with_auth)

print(f"🚀 Success! Groq processed Issue #{num} and opened a new Pull Request on branch {branch}.")