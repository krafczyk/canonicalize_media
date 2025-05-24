#!/bin/bash
input_file="$1"
idx="$2"
output_file="$3"

ffmpeg -hide_banner -i "$input_file" -map "0:$idx" -c:s copy "$output_file"
