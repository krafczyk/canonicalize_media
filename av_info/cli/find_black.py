import argparse
from typing import cast
from av_info.session import MediaContainer
from av_info.ffmpeg_ops import find_black, SeekOptions
from av_info.utils import get_device
import sys


def main() -> None:
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser(
        description="Locate black regions."
    )
    _ = parser.add_argument("--video", help="Path to the video file", type=str, required=True)
    _ = parser.add_argument("--search-start", help="start time", type=str, required=False)
    _ = parser.add_argument("--search-end", help="end time", type=str, required=False)
    _ = parser.add_argument("--mode", help="Change behavior", default="latest_center")
    args = parser.parse_args()

    known_modes = ["latest_center"]
    mode = cast(str, args.mode)
    if mode not in known_modes:
        raise ValueError(f"Invalid mode: {mode}. Known modes are: {known_modes}")

    video_file=cast(str,args.video)
    search_start=cast(str|None, args.search_start)
    search_end = cast(str|None, args.search_end)

    input_media = MediaContainer(video_file)
    input_media.analyze()

    device = get_device()

    seek_options = SeekOptions(input_media.video[0], search_start, search_end, mode="course") 
    seek_options.calibrate(method="ffmpeg", device=device)
    gaps = find_black(
        seek_options,
        device=device,
        verbose=True)

    if mode == "latest_center":
        if not gaps:
            print("No black regions found.")
            sys.exit(-1)
        latest_gap = gaps[-1]
        print((latest_gap.end-latest_gap.start)/2.)
        sys.exit(0)

    else:
        print("Unknown mode, this should not happen.")
        sys.exit(-1)


if __name__ == "__main__":
    main()
