import argparse
from av_info.session import MediaContainer
from av_info.ffmpeg_ops import SeekOptions
from typing import cast
import subprocess


def main() -> None:
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--video", help="Path to the video file", type=str, required=True)
    _ = parser.add_argument("--timestamp", help="Timestamp to capture screenshot at", type=str, required=True)
    _ = parser.add_argument("--output", help="Where to put the image", type=str, required=True)
    args = parser.parse_args()

    video_filepath = cast(str, args.video)

    video_cont = MediaContainer(video_filepath)
    video_cont.analyze()

    timestamp = cast(str, args.timestamp)

    output_filepath = cast(str, args.output)

    seek_options = SeekOptions(video_cont.video[0], start_time=timestamp, mode="course")
    seek_options.calibrate(method="ffmpeg")

    seek_args = seek_options.to_ffmpeg_args()
    cmd = [
        "ffmpeg", "-hide_banner",
        *seek_args["course"],
        *seek_args["input"],
        *seek_args["fine"],
        "-frames:v", "1",
        "-update", "1",
        output_filepath
    ]
    print(f"Running command: {' '.join(cmd)}")
    _ = subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
