#!/usr/bin/env bash
set -euo pipefail

source $(realpath $(dirname $0))/ffmpeg_ops.sh


if [ $# -lt 2 ] || [ $# -gt 2 ]; then
  echo "Usage: $0 <file.mkv> <cut_point>"
  exit 1
fi


file="$1"
cut_point=$(to_seconds "$2")

>&2 echo "File: $file"
>&2 echo "Cut point: $cut_point"

if [ ! -e "$file" ]; then
  echo "File not found: $file"
  exit 1
fi

# Needed for precise split
get_keyframes "$file" keyframes

# Get encoding information for the source
######### 1. probe source ######################################################
readarray -t probe_data < <(
  probe_file "$file"
)

codec="${probe_data[0]}"
pix_fmt="${probe_data[1]}"
duration="${probe_data[2]}"
size="${probe_data[3]}"

hwdec=()          # default: empty  → fall back to CPU decode

case "$codec" in
  hevc*)  hwdec=( -hwaccel cuda -hwaccel_device 1 -c:v hevc_cuvid ) ;;   # handles 8- & 10-bit
  h264*)  hwdec=( -hwaccel cuda -hwaccel_device 1 -c:v h264_cuvid ) ;;
esac

######### 2. compute bitrate ###################################################
bits=$(( size * 8 ))
bps=$(awk "BEGIN {printf \"%d\", $bits / $duration}")   # bits / second
kbps=$(( bps / 1000 ))k                                 # for ffmpeg

echo "kbps: $kbps"

# optional convenience: gather the x265 knobs in shell vars
# These are SDR settings for this particular set of files
x265_p1="pass=1:profile=main10:level=4:no-slow-firstpass=1"
x265_p2="pass=2:profile=main10:level=4:colorprim=bt709:transfer=bt709:colormatrix=bt709"

cut_timepoint=$(to_timecode "$cut_point")

>&2 echo "Cut timepoint: $cut_timepoint"

# include metadata about the source file
meta=( -map 0 -map_metadata 0 -map_chapters 0 )

copy=( -c:a copy -c:s copy -c:t copy )

first_pass_args=(
  -map 0:v:0
  -c:v libx265 -preset slow
  -pix_fmt yuv420p10le
  -b:v "$kbps"
  -profile:v main10 -level:v 4.0
  -x265-params "$x265_p1"
  -an -f null
)

second_pass_args=(
  "${meta[@]}"
  -color_primaries bt709
  -color_trc bt709
  -colorspace bt709
  -c:v libx265 -preset slow
  -pix_fmt yuv420p10le
  -b:v "$kbps"
  -profile:v main10 -level:v 4.0
  -x265-params "$x265_p2"
  "${copy[@]}"
)


set -x
# 1st pass  (analysis only – writes FFmpeg2pass-0.log)
ffmpeg -y "${hwdec[@]}" -i "$file" -to "$cut_timepoint"  \
       "${first_pass_args[@]}" /dev/null

############################################
# 2nd pass  (actual encode)
ffmpeg -y "${hwdec[@]}" -i "$file" -to "$cut_timepoint"   \
       "${second_pass_args[@]}" "Adjusted.$file"
set +x
