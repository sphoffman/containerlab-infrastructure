#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

branch="$(git branch --show-current)"
[[ -n "$branch" ]] || { echo "Cannot push from a detached HEAD."; exit 1; }

if upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null)"; then
    echo
    echo "Commits waiting to be pushed to $upstream:"
    git log --oneline "$upstream"..HEAD
    push_command=(git push)
else
    echo
    echo "Branch '$branch' has no upstream."
    push_command=(git push --set-upstream origin "$branch")
fi

echo
read -r -p "Push these commits to GitHub? [y/N]: " answer
case "$answer" in
    y|Y|yes|YES) "${push_command[@]}"; echo; echo "Push complete." ;;
    *) echo "Push cancelled." ;;
esac
