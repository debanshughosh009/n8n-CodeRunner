import os
import sys
import subprocess as sp
from pathlib import Path

# Extract parameters from n8n execution block
repo, num, title, body = sys.argv[1:5]
branch = f'claude/issue-{num}'
# Specify absolute workspace directory
repo_dir = Path('/mnt/win/Playground/Github Linux/n8n-CodeRunner')

if not repo_dir.exists():
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    sp.run(['git', 'clone', f'git@github.com:{repo}.git', str(repo_dir)], check=True)

os.chdir(repo_dir)

# Standard git sequence
sp.run(['git', 'checkout', 'main'], check=True)
sp.run(['git', 'pull'], check=True)
sp.run(['git', 'checkout', '-B', branch], check=True)

# Run Claude Code in Headless Mode automatically accepting edits
sp.run(['claude', '-p', f'Fix issue #{num}: {title}\n\n{body}', '--permission-mode', 'acceptEdits'], check=True)

# Commit changes and force-push
sp.run(['git', 'add', '.'], check=True)

sp.run(['git', 'commit', '-m', f'Fix issue #{num}'], check=True)
sp.run(['git', 'push', '-u', 'origin', branch, '--force'], check=True)

# Create a Pull Request via GitHub CLI
sp.run([
    'gh', 'pr', 'create',
    '--title', f'Fix issue #{num}: {title}',
    '--body', f'Closes #{num}',
    '--base', 'main',
    '--head', branch
], check=True)