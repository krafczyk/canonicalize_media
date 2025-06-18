#!/usr/bin/env bash
set -euo pipefail


source $(realpath $(dirname "$0"))/ffmpeg_ops.sh


if [ $# -lt 1 ] || [ $# -gt 5 ]; then
  echo "Usage: $0 <file.mkv> [--cut-point <cut_point>] [--split-mode <mode>]"
  exit 1
fi


file="$1"
shift

mode="precise"

known_modes=("simple" "precise")

# simple option parser
while [ $# -gt 0 ]; do
    case "$1" in
        --cut-point)
            [ $# -ge 2 ] || { echo "Error: --cut-point needs a value"; exit 1; }
            cut_point=$2
            shift 2
            ;;
        --split-mode)
            [ $# -ge 2 ] || { echo "Error: --mode needs a value"; exit 1; }
            mode=$2
            if [[ ! " ${known_modes[@]} " =~ " ${mode} " ]]; then
                echo "Error: Unknown split mode '$mode'. Known modes are: ${known_modes[*]}"
                exit 1
            fi
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done


if [ ! -e "$file" ]; then
  echo "File not found: $file"
  exit 1
fi

# Needed for precise split
get_keyframes "$file" keyframes

# Get encoding information for the source
######### 1. probe source ######################################################
readarray -t probe_data < <(probe_file "$file")

codec="${probe_data[0]}"
pix_fmt="${probe_data[1]}"
duration="${probe_data[2]}"
size="${probe_data[3]}"

case "$codec" in
  hevc*)  hwdec=( -hwaccel cuda -hwaccel_device 1 -c:v hevc_cuvid ) ;;   # handles 8- & 10-bit
  h264*)  hwdec=( -hwaccel cuda -hwaccel_device 1 -c:v h264_cuvid ) ;;
esac


if [[ -z ${cut_point+x} ]]; then

  start_min="8"
  start_time=$(echo "$start_min * 60" | bc)

  end_min="14"
  end_time=$(echo "$end_min * 60" | bc)

  start_time=$(closest_keyframe_before "$start_time" keyframes)
  end_time=$(closest_keyframe_after "$end_time" keyframes)

  likely_title_card_time=$(find_image title_card.png -ss $start_time -to $end_time -i "$file")

  >&2 echo "likely title card time: $likely_title_card_time -> $(to_timecode $likely_title_card_time)"

  cut_point=$(find_prior_black "$likely_title_card_time" "$file" 5)
  if [ "$cut_point" == "ERROR" ]; then
    echo "No black frame found before $likely_title_card_time in $file"
    exit 1
  fi
  cut_point=$( echo "$cut_point - 0.1" | bc -l )
fi;

keyframe_before=$(closest_keyframe_before "$cut_point" keyframes)

# Simple mkvmerge split
if [ "$mode" == "simple" ]; then
  echo "Using simple mode: Using keyframe before as cut point"
  keyframe_before_timecode=$(to_timecode "$keyframe_before")
  echo "Using keyframe before as cut point: $keyframe_before_timecode"
  mkvmerge -o "segment_%03d.mkv" \
    --split "timecodes:$keyframe_before_timecode" "$file"
fi

if [ "$mode" == "precise" ]; then
  >&2 echo "Using cut point $cut_point"
  cut_timepoint=$(to_timecode "$cut_point")
  >&2 echo "Cut timepoint: $cut_timepoint"
  # First Half
  precise_reencode segment_001.mkv -i "$file" -to "$cut_timepoint"

  # Second Half
  precise_reencode segment_002.mkv -i "$file" -ss "$cut_timepoint"
fi;

if [ $(ls segment_*.mkv | wc -l) -ne 2 ]; then
  echo "Error: Expected exactly 2 segments, but found $(ls segment_*.mkv | wc -l)." >&2
  exit 1
fi

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
