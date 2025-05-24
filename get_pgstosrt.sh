#!/usr/bin/env bash
set -euo pipefail

repo_url="https://github.com/Tentacule/PgsToSrt"
# strip protocol and .git suffix if present
owner_repo=${repo_url#https://github.com/}
owner_repo=${owner_repo%.git}
api_url="https://api.github.com/repos/${owner_repo}/releases/latest"

echo "Fetching release assets for ${owner_repo}…"
resp=$(curl -fsSL "$api_url")

# pick the first asset whose name ends with .zip
read -r asset_name asset_url < <(
  echo "$resp" \
    | jq -r '
        .assets[]
        | select(.name | endswith(".zip"))
        | "\(.name)\t\(.browser_download_url)"
      ' \
    | head -n1 \
    | tr "\t" " "
)

if [[ -z "$asset_url" ]]; then
  echo "No .zip asset found in latest release."
  exit 1
fi

echo "Downloading asset “$asset_name”…"
curl -fsSL "$asset_url" -o "$asset_name"

echo "Saved as $asset_name"

mkdir PgsToSrt
cd PgsToSrt
unzip "../$asset_name"
