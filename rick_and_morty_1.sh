#!/bin/bash

# scripts to inspect duration differences

#ffprobe -v error -select_streams v:0 -show_format -show_streams "$1"

# format duration tag
#ffprobe -v error -select_streams v:0 -show_entries format=duration "$1"

# stream tag duration
#ffprobe -v error -select_streams v:0 -show_entries stream_tags=DURATION "$1"

# Both tags
ffprobe -v error -select_streams v:0 -show_entries stream_tags=DURATION -show_entries format=duration "$1"


#ffprobe -v error -select_streams v:0 -show_entries \
#        stream=r_frame_rate,DURATION -of csv=p=0 "$1"
