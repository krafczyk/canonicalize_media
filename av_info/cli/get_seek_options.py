import argparse
from av_info.session import MediaContainer
from av_info.ffmpeg_ops import SeekOptions
from typing import cast


def main() -> None:
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser(
        description="Get calibrated seek options for a video file."
    )
    _ = parser.add_argument("--video", help="Path to the video file", type=str, required=True)
    _ = parser.add_argument("--start", help="Start time for seeking", type=str, required=False)
    _ = parser.add_argument("--end", help="End time for seeking", type=str, required=False)
    args = parser.parse_args()

    video_filepath = cast(str, args.video)
    video_cont = MediaContainer(video_filepath)
    video_cont.analyze()

    start_time = cast(str | None, args.start)
    end_time = cast(str | None, args.end)

    seek_options = SeekOptions(video_cont.video[0], start_time=start_time, end_time=end_time, mode="course")
    seek_options.calibrate(method="ffmpeg")

    print(f"Calibrated Seek Options: {" ".join(seek_options.to_ffmpeg_args())}")


if __name__ == "__main__":
    main()
