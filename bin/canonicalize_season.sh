set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <path_to_season_directory> [<other args>...]"
  exit 1
fi;

find "$1" \
  -name "*[sS][0-9][0-9][eE][0-9][0-9]*" \
  -type f \
  \( -name "*.mp4" -or -name "*.mkv" \) \
  -and ! \( -path "*Featurettes*" -or -path "*Extras*" \) \
  -print0 | sort -z | xargs -0 -n1 bash bin/canonicalize_single.sh "${@:2}" -i
