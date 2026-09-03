#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

echo
echo "Current Git status:"
git status --short
echo
read -r -p "Enter commit comment: " commit_message
[[ -n "$commit_message" ]] || { echo "Commit comment cannot be empty."; exit 1; }

git add .
if git diff --cached --quiet; then
    echo "No changes to commit."
    exit 0
fi
git commit -m "$commit_message"
echo
echo "Local commit complete."
git status
