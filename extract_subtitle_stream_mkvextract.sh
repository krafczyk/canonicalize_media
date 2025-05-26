#!/bin/bash
input_file="$1"
idx="$2"
output_file="$3"

mkvextract tracks "$input_file" "$idx:$output_file"
