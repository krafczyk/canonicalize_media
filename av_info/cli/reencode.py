import argparse
from typing import cast
from av_info.session import MediaContainer
from av_info.ffmpeg_ops import reencode, to_timecode
import os


def main() -> None:
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser(
        description="Locate an image in a video file using ffmpeg."
    )
    _ = parser.add_argument("--video", help="Path to the video file", type=str, required=True)
    _ = parser.add_argument("--output", help="Path to put output file", type=str, required=False)
    _ = parser.add_argument("--start", help="start time", type=str, required=False)
    _ = parser.add_argument("--end", help="end time", type=str, required=False)
    _ = parser.add_argument("--device", help="Specify a device", type=int, required=False)
    args = parser.parse_args()

    video_file=cast(str,args.video)
    start=cast(str|None, args.start)
    end=cast(str|None, args.end)
    output=cast(str|None, args.output)

    input_media = MediaContainer(video_file)
    input_media.analyze()

    device = cast(int|None, args.device)

    if not output:
        output_dir = os.path.dirname(video_file)
        output = os.path.join(output_dir, "Adjusted."+os.path.basename(video_file))

    if start:
        start = to_timecode(start)
    if end:
        end = to_timecode(end)
    reencode(input_media, output, start=start, end=end, verbose=True, device=device)

if __name__ == "__main__":
    main()
