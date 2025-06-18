#!/bin/bash
set -euo pipefail

source $(realpath $(dirname $0))/ffmpeg_ops.sh

init_point=$(to_seconds "$1")
input_file="$2"
if [ $# -eq 3 ]; then
  search_window="$3"
fi

readarray -t file_data < <(probe_file "$input_file")

# Needed for precise split
get_keyframes "$input_file" keyframes

codec="${file_data[0]}"

case "$codec" in
  hevc*)  hwdec=( -hwaccel cuda -hwaccel_device 1 -c:v hevc_cuvid ) ;;   # handles 8- & 10-bit
  h264*)  hwdec=( -hwaccel cuda -hwaccel_device 1 -c:v h264_cuvid ) ;;
esac

if [ -z "${search_window:-}" ]; then
  options=( "$init_point" "$input_file" )
else
  options=( "$init_point" "$input_file" "$search_window" )
fi;

cut_point=$(find_prior_black "${options[@]}")
if [ "$cut_point" == "ERROR" ]; then
  echo "No black frame found before $init_point in $input_file"
  exit 1
fi
echo "Closest black frame endpoint: $cut_point -> $(to_timecode $cut_point)"
