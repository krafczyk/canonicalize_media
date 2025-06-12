#!/usr/bin/env bash
set -euo pipefail


to_timecode() {
  local ts=$1        # e.g. 671.67
  # integer‐divide by 60 to get whole minutes
  local mins=$(echo "$ts/60" | bc )
  # subtract (mins*60) to get the leftover seconds (float)
  local secs=$(echo "$ts - ($mins * 60)" | bc -l)
  # format as MM:SS.mmm
  printf "%02d:%06.3f\n" "$mins" "$secs"
}

fix_timecode() {
  local time_diff="$1"
  if [[ $time_diff == .* ]]; then
    echo "0$time_diff"
  else
    echo "$time_diff"
  fi
}

get_keyframes() {
  local file="$1"
  local -n keyfs="$2"
  readarray -t keyfs < <(ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=print_section=0 "$file" | grep K | awk -F, '{ print $1 }')
}

closest_keyframe_before() {
  local target_time="$1"
  local -n keyfs="$2"
  
  local closest_time=0
  for kf in "${keyfs[@]}"; do
    if (( $(echo "$kf <= $target_time" | bc -l) )); then
      closest_time="$kf"
    else
      break
    fi
  done

  echo "$closest_time"
}

closest_keyframe_after() {
  local target_time="$1"
  local -n keyfs="$2"
  
  local closest_time=0
  for kf in "${keyfs[@]}"; do
    if (( $(echo "$kf >= $target_time" | bc -l) )); then
      closest_time="$kf"
      break
    fi
  done

  echo "$closest_time"
}


if [ $# -gt 2 -o $# -eq 0 ]; then
  echo "Usage: $0 <file.mkv> [<cut_point>]"
  exit 1
fi

file="$1"

if [ ! -e "$file" ]; then
  echo "File not found: $file"
  exit 1
fi

# Needed for precise split
get_keyframes "$file" keyframes

if [ $# -eq 1 ]; then

  start_min="8"
  start_time=$(echo "$start_min * 60" | bc)

  end_min="14"
  end_time=$(echo "$end_min * 60" | bc)

  start_time=$(closest_keyframe_before "$start_time" keyframes)
  end_time=$(closest_keyframe_after "$end_time" keyframes)

  frame_step="5"

  set -x
  # Coarse title card search
  ffmpeg -hide_banner -nostats -hwaccel cuda -c:v hevc_cuvid -ss $start_time -to $end_time -i "$file" -i title_card.png -filter_complex "[0:v]framestep=$frame_step[sampled];[sampled][1:v]ssim=stats_file=ssim_output.txt" -f null - >& /dev/null
  set +x

  mapfile -t frame_n < <(cat ssim_output.txt | awk '{ print $1 }' | cut -b 3-)
  mapfile -t ssim < <(cat ssim_output.txt | awk '{ gsub(/[()]/, "", $6); print $6 }')

  best_sim=0
  best_frame=0
  for i in "${!frame_n[@]}"; do
    if (( $(echo "${ssim[i]} > $best_sim" | bc -l) )); then
      best_sim="${ssim[i]}"
      best_frame="${frame_n[i]}"
    fi
  done

  echo "best_sim: $best_sim at frame: $best_frame"

  likely_title_card_time=$(echo "$start_time + (($best_frame * $frame_step) / 24)" | bc -l)

  echo "likely title card time: $(to_timecode $likely_title_card_time)"

  # Find black frame before the title card

  search_window="3"
  min_width="0.01"
  thresh="0.01"

  start_time=$(echo "$likely_title_card_time - $search_window" | bc -l)
  start_time=$(closest_keyframe_before "$start_time" keyframes)
  start_timecode=$(to_timecode "$start_time")

  end_time=$(closest_keyframe_after "$likely_title_card_time" keyframes)
  end_timecode=$(to_timecode "$end_time")

  echo "Searching for black frames in the range $start_time to $end_time"

  ffmpeg -hide_banner -nostats -hwaccel cuda -c:v hevc_cuvid -ss "$start_timecode" -to $end_timecode -i "$file" -vf blackdetect=d=$min_width:pix_th=$thresh -an -f null - 2>&1 | awk '/black_start/' > blackdata.txt

  mapfile -t endpoints < <(cat blackdata.txt | awk '{ print $5 }' | awk -F: '{ print $2 }')

  # Find the closest endpoint to the likely title card time
  closest_endpoint=9999
  for el in "${endpoints[@]}"; do
    endpoint_time=$(echo "$el + $start_time" | bc -l)
    if (( $(echo "$endpoint_time < $likely_title_card_time" | bc -l) )); then
      time_diff=$(echo "$likely_title_card_time - $endpoint_time" | bc -l)
      if (( $(echo "$time_diff < $closest_endpoint" | bc -l) )); then
        closest_endpoint="$endpoint_time"
      fi
    fi
  done

  echo "Closest black frame endpoint: $closest_endpoint -> $(to_timecode $closest_endpoint)"
  cut_point=$( echo "$closest_endpoint - 0.1" | bc -l )

else
  cut_point="$2"
fi;

echo "Cut point: $cut_point"

keyframe_before=$(closest_keyframe_before "$cut_point" keyframes)

keyframe_after=$(closest_keyframe_after "$cut_point" keyframes)

first_part_diff=$(echo "$cut_point - $keyframe_before" | bc -l)

# If the first_part_diff is small enough, we can just use keyframe before as the cut point
#if (( $(echo "$first_part_diff < 0.2" | bc -l) )); then
if true; then

  keyframe_before_timecode=$(to_timecode "$keyframe_before")
  echo "Using keyframe before as cut point: $keyframe_before_timecode"
  mkvmerge -o "segment_%03d.mkv" \
    --split "timecodes:$keyframe_before_timecode" "$file"

else
  second_part_diff=$(echo "$keyframe_after - $cut_point" | bc -l)

  echo "$first_part_diff"
  echo "$second_part_diff"
  # add a 0 in front of results < 1 second. They are reported like '.123'
  first_part_diff=$(fix_timecode "$first_part_diff")
  second_part_diff=$(fix_timecode "$second_part_diff")
  echo "$first_part_diff"
  echo "$second_part_diff"

  # Choose encoder
  codec=$(ffprobe -v error -select_streams v:0 \
                  -show_entries stream=codec_name \
                  -of csv=p=0 "$file")

  case "$codec" in
    h264) venc=(-c:v libx264 -crf 0 -preset veryfast) ;;
    hevc) venc=(-c:v libx265 -x265-params lossless=1 -preset fast) ;;
    vp9)  venc=(-c:v libvpx-vp9 -lossless 1) ;;
    *)    echo "Unknown/unsupported codec: $codec" && exit 1 ;;
  esac
  # audio/subs always copied
  acopy=(-c:a copy -c:s copy)

  cut_timecode=$(to_timecode "$cut_point")
  keyframe_before_timecode=$(to_timecode "$keyframe_before")
  keyframe_after_timecode=$(to_timecode "$keyframe_after")

  echo "▶ building first half …"

  # Copy up to the key-frame that begins the boundary GOP
  set -x
  ffmpeg -y -v error -to "$keyframe_before_timecode" -i "$file" \
         -map 0 -c copy -avoid_negative_ts make_zero \
         part_1.mkv

  # Loss-less re-encode keyframe_before - cut_point
  ffmpeg -y -v error -ss "$keyframe_before_timecode" -i "$file" -t "$first_part_diff" -map 0 "${venc[@]}" "${acopy[@]}" -avoid_negative_ts make_zero part_2.mkv

  # Merge the two parts
  mkvmerge -o "segment_1.mkv" \
           part_1.mkv + part_2.mkv

  "Incomplete splitting section!!"
  exit 1
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
