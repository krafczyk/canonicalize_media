#!/bin/bash

left="$1"
right="$2"
timestamp="$3"
output="$4"


ffmpeg \
  -ss "$timestamp" -i "$left" \
  -ss "$timestamp" -i "$right" \
  -filter_complex "\
    [0:v]drawtext=text='Left':x=10:y=10:fontsize=36:fontcolor=white@0.5[left]; \
    [1:v]drawtext=text='Right':x=10:y=10:fontsize=36:fontcolor=white@0.5[right]; \
    [left][right]hstack=inputs=2[top]; \
    [0:v][1:v]blend=all_mode=difference:all_opacity=1[diffraw]; \
    [diffraw]drawtext=text='Diff':x=10:y=10:fontsize=36:fontcolor=white@0.5[diff]; \
    [diff]pad=2*iw:ih:iw/2:0:color=black[diffpadded]; \
    [top][diffpadded]vstack=inputs=2[out]" \
  -map "[out]" -frames:v 1 "$output"
