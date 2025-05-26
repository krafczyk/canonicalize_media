#!/usr/bin/env bash
# fix_dash.sh
# Scan for filenames using an en-dash (–) and replace it with a plain hyphen (-).
# Usage: fix_dash.sh [-n|--dry-run] [directory]

shopt -s extglob

dry_run=0

# Parse options
while [[ "$1" == -* ]]; do
  case "$1" in
    -n|--dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [-n|--dry-run] [directory]"
      echo
      echo "  -n, --dry-run   Show what would be renamed without performing the move"
      echo "  directory       Root directory to scan (default: current directory)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Directory to scan (default = current)
SEARCH_DIR="${1:-.}"

# Supported extensions
EXTENSIONS="mkv mp4 avi mov wmv flac iso json"

# Find all files containing an en-dash
find "$SEARCH_DIR" -type f -name "*–*" | while IFS= read -r src; do
  filename="${src##*/}"

  # Match: <Title> (<Year>) – <Resolution>.<ext>
  if [[ "$filename" =~ ^(.+)\ \(([0-9]{4})\)\ –\ ([^\.]+)\.([^.]+)$ ]]; then
    title="${BASH_REMATCH[1]}"
    year="${BASH_REMATCH[2]}"
    res="${BASH_REMATCH[3]}"
    ext="${BASH_REMATCH[4]}"

    # Skip unsupported extensions
    if ! [[ " $EXTENSIONS " =~ " $ext " ]]; then
      continue
    fi

    newname="${title} (${year}) - ${res}.${ext}"
    dst="${src%/*}/$newname"

    if [[ -e "$dst" ]]; then
      echo "SKIP: target exists → $newname"
    else
      if [[ $dry_run -eq 1 ]]; then
        echo "DRY-RUN: would rename"
        echo "  from: $filename"
        echo "  to:   $newname"
      else
        echo "RENAMING:"
        echo "  from: $filename"
        echo "  to:   $newname"
        mv -- "$src" "$dst"
      fi
    fi
  fi
 done
