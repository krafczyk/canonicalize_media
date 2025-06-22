#!/bin/bash
set -euo pipefail

source $(realpath $(dirname $0))/ffmpeg_ops.sh

input_file=$(find_input_file "$@")

readarray -t file_data < <(probe_file "$input_file")

# Needed for precise split
get_keyframes "$input_file" keyframes

codec="${file_data[0]}"
pix_fmt="${file_data[1]}"
duration="${file_data[2]}"
size="${file_data[3]}"

case "$codec" in
  hevc*)  hwdec=( -hwaccel cuda -hwaccel_device 1 -c:v hevc_cuvid ) ;;   # handles 8- & 10-bit
  h264*)  hwdec=( -hwaccel cuda -hwaccel_device 1 -c:v h264_cuvid ) ;;
esac

precise_reencode "$@"
