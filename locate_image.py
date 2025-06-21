import argparse
from typing import cast
from av_info.session import MediaContainer
from av_info.ffmpeg_ops import get_keyframe_times, find_image, SeekOptions, to_timecode, find_black
from av_info.utils import get_device
import sys


if __name__ == "__main__":
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser(
        description="Locate an image in a video file using ffmpeg."
    )
    _ = parser.add_argument("--image", help="Path to the image to locate", type=str, required=True)
    _ = parser.add_argument("--video", help="Path to the video file", type=str, required=True)
    _ = parser.add_argument("--search-start", help="start time", type=str, required=False)
    _ = parser.add_argument("--search-end", help="end time", type=str, required=False)
    _ = parser.add_argument("--mode", help="Change behavior", default="best")
    args = parser.parse_args()

    image_path=cast(str,args.image)
    video_file=cast(str,args.video)
    search_start=cast(str, args.search_start)
    arg_search_end = cast(str|None, args.search_end)

    input_media = MediaContainer(video_file)
    input_media.analyze()

    device = get_device()

    keyframes = get_keyframe_times(input_media.video[0])

    seek_options = SeekOptions(input_media.video[0], search_start, arg_search_end, mode="course") 
    seek_options.calibrate(method="ffmpeg", device=device)

    likely_location = find_image(
        seek_options,
        image_path,
        device=device,
        mode=cast(str, args.mode),
        verbose=True)

    if likely_location < 0.:
        print("Image not found in the video.")
        sys.exit(1)

    print(f"{to_timecode(likely_location)}")
    sys.exit(0)
