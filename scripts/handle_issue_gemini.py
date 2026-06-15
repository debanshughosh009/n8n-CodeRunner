import os
import sys
import json
import subprocess as sp
from pathlib import Path
from google import genai
from google.genai import types

# Extract parameters from n8n execution block
repo, num, title, body = sys.argv[1:5]
branch = f'gemini/issue-{num}'
repo_dir = Path('/mnt/win/Playground/Github Linux/n8n-CodeRunner')

if not repo_dir.exists():
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    sp.run(['git', 'clone', f'git@github.com:{repo}.git', str(repo_dir)], check=True)

os.chdir(repo_dir)

# Standard git sequence
sp.run(['git', 'checkout', 'main'], check=True)
sp.run(['git', 'pull'], check=True)
sp.run(['git', 'checkout', '-B', branch], check=True)

# --- GEMINI API INTEGRATION ---
# Initialize client (looks for GEMINI_API_KEY environment variable)
client = genai.Client()

prompt = f"""
You are an automated code fixer. Fix the following repository issue.
Issue #{num}: {title}
Description: {body}

Look at the repository files and provide the necessary fixes. 
You must respond ONLY with a JSON array of objects representing the file changes, using this exact schema:
[
  {{
    "filepath": "relative/path/to/file.py",
    "content": "The entire new content of the file..."
  }}
]
Do not include markdown code blocks (like ```json) in your response, just raw JSON.
"""

# Call the API using gemini-2.5-flash
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=prompt,
)

# Parse Gemini's response and overwrite the local files
try:
    # Clean up any potential markdown formatting if the model slipped up
    raw_json = response.text.strip().removeprefix('```json').removesuffix('```').strip()
    file_changes = json.loads(raw_json)
    
    for change in file_changes:
        target_file = repo_dir / change['filepath']
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(change['content'], encoding='utf-8')
        print(f"Successfully updated: {change['filepath']}")
        
except Exception as e:
    print(f"Failed to automatically apply Gemini's edits. Error: {e}")
    print(f"Model response was:\n{response.text}")
    sys.exit(1)
# --------------------------------

# Commit changes and force-push
sp.run(['git', 'add', '.'], check=True)
sp.run(['git', 'commit', '-m', f'Fix issue #{num} via Gemini API'], check=True)
sp.run(['git', 'push', '-u', 'origin', branch, '--force'], check=True)

# Create a Pull Request via GitHub CLI
sp.run([
    'gh', 'pr', 'create',
    '--title', f'Fix issue #{num}: {title}',
    '--body', f'Closes #{num}. Automated fix by Gemini API.',
    '--base', 'main',
    '--head', branch
], check=True)