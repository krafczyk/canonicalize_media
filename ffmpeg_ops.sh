hwdec=()          # default: empty  → fall back to CPU decode


to_timecode() {
  # Usage: to_timecode <time_input> -> <timecode_output>
  # Translate first argument to a timecode string in HH:MM:SS.mmm format.
  # Hours may be elided if 0.
  # function should be idempotent.

  local ts=$1        # e.g. 671.67
  # If the input has a ':', it's probably already a timecode, don't do anything
  if [[ "$ts" == *:* ]]; then
    echo "$ts"
    return 0
  fi
  # integer‐divide by 60 to get whole minutes
  local mins=$(echo "$ts/60" | bc )
  # subtract (mins*60) to get the leftover seconds (float)
  local secs=$(echo "$ts - ($mins * 60)" | bc -l)
  # format as MM:SS.mmm
  printf "%02d:%06.3f\n" "$mins" "$secs"
}

count_chars() {
  # Usage: count_chars <str> <target_char>
  # Count the number of occurrences of <target_char> in <str>.

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
  # Usage: to_seconds <time_input> -> <time_in_seconds>
  # Translate a timecode string in HH:MM:SS.mmm or similar formats to seconds.
  # Should be idempotent.

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

get_keyframe_times() {
    # Usage: get_keyframe_times "path/to/video.mp4" keyframe_array_name
    # Populates an array with keyframe timestamps (in seconds) from a video file.

    local file="$1"
    # Using a nameref to modify the array in the caller's scope.
    local -n keyframe_times_ref="$2"

    # This command is more robust. It uses awk to find packets with the 'K' flag
    # and print only the timestamp.
    readarray -t keyframe_times_ref < <(
        ffprobe -v error -select_streams v:0 \
                -show_entries packet=pts_time,flags \
                -of csv=p=0 "$file" | awk -F, '/,K/ {print $1}'
    )
}

closest_keyframe_before() {
    # Usage: closest_keyframe_before <target_time> keyframe_array_name
    # Finds the keyframe timestamp immediately BEFORE or AT the target time.
    # This is much faster than looping in Bash.

    local target_time="$1"
    local -n keyfs="$2"
    
    # Print the array and pipe to awk for efficient float-aware searching.
    printf "%s\n" "${keyfs[@]}" | \
    awk -v target="$target_time" '
        # Store the last known keyframe that is less than or equal to the target.
        $1 <= target { last_valid = $1 }
        # Since the list is sorted, we can stop as soon as we pass the target.
        $1 > target { exit }
        END { if (last_valid != "") print last_valid; else print 0 }
    '
}

closest_keyframe_after() {
    # Usage: closest_keyframe_after <target_time> keyframe_array_name
    # Finds the first keyframe timestamp immediately AFTER or AT the target time.

    local target_time="$1"
    local -n keyfs="$2"
    
    printf "%s\n" "${keyfs[@]}" | \
    awk -v target="$target_time" '
        # Print the first keyframe that is greater than or equal to the target and exit.
        $1 >= target { print $1; exit }
    '
}

## Gets the precise presentation timestamp (in seconds) for a specific frame number (0-indexed).
## This is crucial for mapping filter results (like blackdetect) to timecodes.
## Usage: get_timecode_for_frame "path/to/video.mp4" <frame_number>
#get_timecode_for_frame() {
#    local file="$1"
#    local frame_num=$2
#    # awk's line numbers (NR) are 1-indexed, so we add 1.
#    local awk_line_num=$((frame_num + 1))
#
#    ffprobe -v error -select_streams v:0 \
#            -show_entries frame=best_effort_timestamp_time \
#            -of default=noprint_wrappers=1:nokey=1 "$file" |
#    awk -v line="$awk_line_num" 'NR==line {print; exit}'
#}

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
  # Usage: find_image <image_path> [-ss <start_time> -to <end_time>] -i <input_file> [-ss <fine_seek> -to <end_time> ]
  # Finds the rough spot a given image appears in a video file.

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


find_first_occurance_noblack() {
  local image_path="$1"
  shift

  local start_time="0"

  if [ "$1" == "-ss" ]; then
    start_time="$2"
  fi

  # Get start time from the first keyframe
  if [[ "$start_time" == "0" ]]; then
    start_time=$(closest_keyframe_before "$start_time" keyframes)
  fi

  # image search
  ffmpeg -hide_banner -nostats "${hwdec[@]}" "$@" -i "$image_path" -filter_complex "ssim=stats_file=ssim_output.txt" -f null -

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

  thresh="0.5"
  first_frame="$best_frame"
  # Inspect frames backwards from the 'best' frame until similarity
  # drops to thresh*best_sim or we reach the start of the video
  for (( i = best_frame; i >= 0; i-- )); do
    if (( $(echo "${ssim[i]} < $thresh * $best_sim" | bc -l) )); then
      break
    fi
    first_frame=$i
  done

  start_time=$(to_seconds "$start_time")

  likely_image_time=$(echo "$start_time + ($best_frame / 24)" | bc -l)
  echo $(to_timecode "$likely_image_time")
}


find_prior_black() {
  # Find black frame before the title card
  # $1: initial guess
  # $2: file
  # [$3]: search_window

  guess_time=$(to_seconds "$1")
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

    if (( $(echo "$end_time < $start_time" | bc -l) )); then
      exit 1
    fi
    end_timecode=$(to_timecode "$end_time")

    time_spec=(-ss "$start_timecode" -to "$end_timecode")
  else
    end_time="$guess_time"
    end_timecode=$(to_timecode "$end_time")

    time_spec=(-to "$end_timecode")
  fi

  min_width="0.1"
  thresh="0.1"

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

  if [[ "$closest_endpoint" == "9999" ]]; then
    >&2 echo "No black frame found before the title card."
    echo "ERROR"
  fi

  echo "$closest_endpoint"
}

precise_reencode() {
  output_file="$1"
  shift

  ######### 2. compute bitrate ###################################################
  bits=$(( size * 8 ))
  bps=$(awk "BEGIN {printf \"%d\", $bits / $duration}")   # bits / second
  kbps=$(( bps / 1000 ))k                                 # for ffmpeg

  # optional convenience: gather the x265 knobs in shell vars
  # These are SDR settings for this particular set of files
  x265_p1="pass=1:profile=main10:level=4:no-slow-firstpass=1"
  x265_p2="pass=2:profile=main10:level=4:colorprim=bt709:transfer=bt709:colormatrix=bt709"

  cut_timepoint=$(to_timecode "$cut_point")

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


  # First Half

  set -x
  ############################################
  # 1st pass  (analysis only – writes FFmpeg2pass-0.log)
  ffmpeg -y "${hwdec[@]}" "$@" \
         "${first_pass_args[@]}" /dev/null

  ############################################
  # 2nd pass  (actual encode)
  ffmpeg -y "${hwdec[@]}" "$@" \
         "${second_pass_args[@]}" "$output_file"
  set +x
}
