hwdec=()          # default: empty  → fall back to CPU decode


to_timecode() {
  local ts=$1        # e.g. 671.67
  # integer‐divide by 60 to get whole minutes
  local mins=$(echo "$ts/60" | bc )
  # subtract (mins*60) to get the leftover seconds (float)
  local secs=$(echo "$ts - ($mins * 60)" | bc -l)
  # format as MM:SS.mmm
  printf "%02d:%06.3f\n" "$mins" "$secs"
}

count_chars() {
  local str="$1"
  local target_char="$2"
  local count=0
  while read -n1 char; do
    if [[ "$char" == "$target_char" ]]; then
      ((count++))
    fi
  done <<< "$str"
  echo "$count"
}

to_seconds() {
  local timecode="$1"  # e.g. "01:11:11.123"
  num_chars=$(count_chars "$timecode" ":")

  if (( num_chars > 2 )); then
    >&2 echo "Timecode has more than 2 colons, invalid format"
    return 1
  fi

  local hours=0
  local minutes=0
  local seconds=0
  if (( num_chars == 2 )); then
    hours=$(echo "$timecode" | cut -d':' -f1)
    minutes=$(echo "$timecode" | cut -d':' -f2)
    seconds=$(echo "$timecode" | cut -d':' -f3)
  elif (( num_chars == 1 )); then
    minutes=$(echo "$timecode" | cut -d':' -f1)
    seconds=$(echo "$timecode" | cut -d':' -f2)
  elif (( num_chars == 0 )); then
    seconds="$timecode"
  else
    >&2 echo "Invalid timecode format: $timecode"
    return 1
  fi
  math="$hours * 3600 + $minutes * 60 + $seconds"
  echo "$math" | bc -l
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

find_input_file() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -i)
        echo "$2"
        break
        ;;
      *)
        shift
        ;;
    esac
  done
}

probe_file() {
  # Get encoding information for the source
  ffprobe -v error \
          -select_streams v:0 \
          -show_entries format=duration,size \
          -show_entries stream=codec_name,pix_fmt \
          -of default=noprint_wrappers=1:nokey=1 "$1"
}


find_image() {
  local image_path="$1"
  shift

  local start_time="0"

  if [ "$1" == "-ss" ]; then
    start_time="$2"
  fi

  frame_step="5"
  # Get start time from the first keyframe
  if [[ "$start_time" == "0" ]]; then
    start_time=$(closest_keyframe_before "$start_time" keyframes)
  fi

  frame_step="5"
  # Coarse title card search
  ffmpeg -hide_banner -nostats "${hwdec[@]}" "$@" -i "$image_path" -filter_complex "[0:v]framestep=$frame_step[sampled];[sampled][1:v]ssim=stats_file=ssim_output.txt" -f null -

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

  start_time=$(to_seconds "$start_time")

  likely_image_time=$(echo "$start_time + (($best_frame * $frame_step) / 24)" | bc -l)
  echo $(to_timecode "$likely_image_time")
}


find_prior_black() {
  # Find black frame before the title card
  # $1: initial guess
  # $2: file
  # [$3]: search_window

  guess_time="$1"
  file="$2"
  if [[ -z "$3" ]]; then
    search_window=""
  else
    search_window="$3"
  fi

  time_spec=()

  if [[ -n "$search_window" ]]; then
    start_time=$(echo "$guess_time - $search_window" | bc -l)
    start_time=$(closest_keyframe_before "$start_time" keyframes)
    start_timecode=$(to_timecode "$start_time")

    end_time=$(closest_keyframe_after "$guess_time" keyframes)
    if [ "$end_time" == "0" ]; then
      end_time="$guess_time"
    fi

    if [ end_time < start_time ]; then
      exit 1
    fi
    end_timecode=$(to_timecode "$end_time")

    time_spec=(-ss "$start_timecode" -to "$end_timecode")
  else
    end_time="$guess_time"
    end_timecode=$(to_timecode "$end_time")

    time_spec=(-to "$end_timecode")
  fi

  min_width="0.01"
  thresh="0.01"

  set -x
  ffmpeg -hide_banner -nostats -hwaccel cuda -c:v hevc_cuvid "${time_spec[@]}" -i "$file" -vf blackdetect=d=$min_width:pix_th=$thresh -an -f null - 2>&1 | awk '/black_start/' > blackdata.txt
  set +x

  mapfile -t endpoints < <(cat blackdata.txt | awk '{ print $5 }' | awk -F: '{ print $2 }')

  # Find the closest endpoint to the likely title card time
  closest_endpoint=9999
  for el in "${endpoints[@]}"; do
    endpoint_time=$(echo "$el + $start_time" | bc -l)
    if (( $(echo "$endpoint_time < $guess_time" | bc -l) )); then
      time_diff=$(echo "$guess_time - $endpoint_time" | bc -l)
      if (( $(echo "$time_diff < $closest_endpoint" | bc -l) )); then
        closest_endpoint="$endpoint_time"
      fi
    fi
  done

  echo "$closest_endpoint"
}
