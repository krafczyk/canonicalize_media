#!/bin/bash

movie_dir="/data1/media_server/TV Shows"
rm_dir_1="Rick and Morty"
rm_dir_2="Rick.and.Morty.S01.1080p.BluRay.x265-RARBG"

readarray -t rm_1 < <(find "$movie_dir/$rm_dir_1" -type f -path "*Season 01*" \( -name "*mkv" -or -name "*mp4" \) -not \( -path "*Sample*" -or -path "*Extras*" \) | sort)
readarray -t rm_2 < <(find "$movie_dir/$rm_dir_2" -type f \( -name "*mkv" -or -name "*mp4" \) | sort)


get_bitdepth() {
  local -n files="$1"
  for file in "${files[@]}"; do
    mediainfo "$file" | grep "Bit depth" | cut -d: -f 2 | awk '{print $1}'
  done;
}

echo "Version 1 Bit Depths: $(get_bitdepth rm_1 | uniq)"
echo "Version 2 Bit Depths: $(get_bitdepth rm_2 | uniq)"

duration_comparison() {
  file1="$1"
  file2="$2"
  echo "Comparing durations for $file1 and $file2"
  duration_1=$(mediainfo "$file1" | grep "Duration" | cut -d: -f 2)
  duration_2=$(mediainfo "$file2" | grep "Duration" | cut -d: -f 2)
  echo "$duration_1 $duration_2"
}

duration_comparison "${rm_1[0]}" "${rm_2[0]}"

#for (( i=0; i<${#rm_1[@]}; i++ )); do
#    file_1="${rm_1[$i]}"
#    file_2="${rm_2[$i]}"
#    mediainfo "$file_1" | grep "Bit depth" | cut -d: -f 2 | awk '{print $1}' | uniq
#    mediainfo "$file_2" | grep "Bit depth" | cut -d: -f 2 | awk '{print $1}' | uniq
#done
