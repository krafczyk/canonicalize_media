#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: $0 <timecodes> <file.mkv>"
  exit 1
fi

timecodes="$1"
file="$2"

# 1) Split the file into two segments
mkvmerge \
  --output 'segment_%03d.mkv' \
  --split timecodes:"$timecodes" \
  "$file"

# 2) Parse the original filename
filename="$(basename "$file")"
base="${filename%.mkv}"

# Expect: Show Name (Year) - SXXEYY-EZZ - TitleY & TitleZ (…metadata…)
if [[ $base =~ ^(.+)\ -\ (S[0-9]{2}E[0-9]{2}-E?[0-9]{2})\ -\ (.+)\ \&\ (.+)\ (\(.*\))$ ]]; then
  show="${BASH_REMATCH[1]}"
  ep_range="${BASH_REMATCH[2]}"
  title1="${BASH_REMATCH[3]}"
  title2="${BASH_REMATCH[4]}"
  metadata="${BASH_REMATCH[5]}"
else
  echo "Error: filename does not match expected pattern." >&2
  exit 1
fi

# 3) Extract season & episode numbers
#    from ep_range like "S03E06-E07" or "S03E06-E07"
if [[ $ep_range =~ ^S([0-9]{2})E([0-9]{2})-E?([0-9]{2})$ ]]; then
  season="${BASH_REMATCH[1]}"
  ep1="${BASH_REMATCH[2]}"
  ep2="${BASH_REMATCH[3]}"
else
  echo "Error: episode range doesn’t match SXXEYY-EZZ format." >&2
  exit 1
fi

first_code="S${season}E${ep1}"
second_code="S${season}E${ep2}"

# 4) Rename the split files
mv segment_001.mkv "${show} - ${first_code} - ${title1} ${metadata}.mkv"
mv segment_002.mkv "${show} - ${second_code} - ${title2} ${metadata}.mkv"

echo "Done! Created:"
echo "  • ${show} - ${first_code} - ${title1} ${metadata}.mkv"
echo "  • ${show} - ${second_code} - ${title2} ${metadata}.mkv"
