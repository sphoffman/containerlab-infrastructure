#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
labmgmt_path="$repo_root/scripts/labmgmt"

missing=()
python3 -c 'import yaml' >/dev/null 2>&1 || missing+=("python3-yaml")
python3 -c 'import ruamel.yaml' >/dev/null 2>&1 || missing+=("python3-ruamel.yaml")
if (( ${#missing[@]} )); then
    echo "Missing Python dependencies: ${missing[*]}"
    echo "Install with: sudo apt install python3 ${missing[*]}"
    exit 1
fi

chmod +x "$repo_root/scripts/labmgmt" "$repo_root/scripts/commit-lab.sh" "$repo_root/scripts/push-labs.sh" "$repo_root/scripts/install.sh"
mkdir -p "$repo_root/labs" "$repo_root/labmgmt/ipam/labs" "$repo_root/labmgmt/ipam/archive/labs" "$repo_root/labmgmt/generated/dns"
sudo ln -sfn "$labmgmt_path" /usr/local/bin/labmgmt
echo "Installed: /usr/local/bin/labmgmt -> $labmgmt_path"
echo "Next: review $repo_root/labmgmt/config.yml and run 'labmgmt validate'."
