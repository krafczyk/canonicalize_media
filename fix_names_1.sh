#!/usr/bin/env bash
shopt -s extglob

# Change this to wherever your files are:
SEARCH_DIR="${1:-.}"

# File extensions to process:
EXTENSIONS="mkv|mp4|avi|mov|wmv|flac|iso|json"

find "$SEARCH_DIR" -type f \
  -regextype posix-extended \
  -regex ".*/(.+) \(([0-9]{4})\) \[([^^/]+)\]\.($EXTENSIONS)$" \
| while read -r src; do
    # Extract components via bash regex
    filename="${src##*/}"
    if [[ "$filename" =~ ^(.+)\ \(([0-9]{4})\)\ \[([^\]]+)\]\.([^.]+)$ ]]; then
      title="${BASH_REMATCH[1]}"
      year="${BASH_REMATCH[2]}"
      res="${BASH_REMATCH[3]}"
      ext="${BASH_REMATCH[4]}"

      newname="${title} (${year}) – ${res}.${ext}"
      dst="${src%/*}/$newname"

      if [[ -e "$dst" ]]; then
        echo "SKIP: target exists → $newname"
      else
        echo "RENAMING:"
        echo "  from: $filename"
        echo "  to:   $newname"
        mv -- "$src" "$dst"
      fi
    fi
  done
