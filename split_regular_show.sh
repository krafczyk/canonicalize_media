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


if [ $# -lt 1 ] || [ $# -gt 5 ]; then
  echo "Usage: $0 <file.mkv> [--cut-point <cut_point>] [--split-mode <mode>]"
  exit 1
fi


file="$1"
shift

mode="simple"

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
readarray -t probe_data < <(
  ffprobe -v error \
          -select_streams v:0 \
          -show_entries format=duration,size \
          -show_entries stream=codec_name,pix_fmt \
          -of default=noprint_wrappers=1:nokey=1 "$file"
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


if [[ -z ${cut_point+x} ]]; then

  start_min="8"
  start_time=$(echo "$start_min * 60" | bc)

  end_min="14"
  end_time=$(echo "$end_min * 60" | bc)

  start_time=$(closest_keyframe_before "$start_time" keyframes)
  end_time=$(closest_keyframe_after "$end_time" keyframes)

  frame_step="5"

  set -x
  # Coarse title card search
  ffmpeg -hide_banner -nostats "${hwdec[@]}" -ss $start_time -to $end_time -i "$file" -i title_card.png -filter_complex "[0:v]framestep=$frame_step[sampled];[sampled][1:v]ssim=stats_file=ssim_output.txt" -f null - >& /dev/null
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

fi;

echo "Cut point: $cut_point"
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
  ffmpeg -y "${hwdec[@]}" -i "$file" -to "$cut_timepoint" \
         "${first_pass_args[@]}" /dev/null

  ############################################
  # 2nd pass  (actual encode)
  ffmpeg -y "${hwdec[@]}" -i "$file" -to "$cut_timepoint" \
         "${second_pass_args[@]}" segment_001.mkv

  # Second Half
  # 1st pass  (analysis only – writes FFmpeg2pass-0.log)
  ffmpeg -y "${hwdec[@]}" -i "$file" -ss "$cut_timepoint"  \
         "${first_pass_args[@]}" /dev/null

  ############################################
  # 2nd pass  (actual encode)
  ffmpeg -y "${hwdec[@]}" -i "$file" -ss "$cut_timepoint"   \
         "${second_pass_args[@]}" segment_002.mkv
  set +x
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
