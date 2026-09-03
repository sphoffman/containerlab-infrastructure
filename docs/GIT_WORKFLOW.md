# Git workflow

The helpers discover the repository from their own location; no clone path is hardcoded.

```bash
git status
git diff
scripts/commit-lab.sh
scripts/push-labs.sh
```

Commit and push remain separate deliberately. `commit-lab.sh` uses `git add .`, so review changes and ignore rules first.
