if [ ! -e "$1" ]; then
  echo "Usage: $0 <video_file>"
  echo "Please provide a valid video file."
  exit 1
fi;

ffmpeg -ss 11:00 -to 12:00 -i "$1" -vf fps=1 -y frame_%04d.png; feh frame_*.png; rm frame*.png;
