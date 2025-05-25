#!/usr/bin/env bash
# metadata.sh <title> <year> [movie|series]
TITLE="$1"
#YEAR="$2"
TYPE="${3:-movie}"   # default to movie

if [[ -z "$OMDB_API_KEY" ]]; then
  echo "Please set \$OMDB_API_KEY first." >&2
  exit 1
fi

case "$TYPE" in
  movie)
    URL="http://www.omdbapi.com/?t=$(printf %s "$TITLE" | jq -sRr @uri)&apikey=$OMDB_API_KEY"
    ;;
  series)
    URL="http://www.omdbapi.com/?t=$(printf %s "$TITLE" | jq -sRr @uri)&type=series&apikey=$OMDB_API_KEY"
    ;;
  *)
    echo "Unknown type: $TYPE" >&2
    exit 1
    ;;
esac

curl -s "$URL" | jq
