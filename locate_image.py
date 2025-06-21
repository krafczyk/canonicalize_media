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
        verbose=True)

    if likely_location < 0.:
        print("Image not found in the video.")
        sys.exit(1)

    print(f"The image is likely located at: {likely_location:.2f} seconds -> {to_timecode(likely_location)}")

    sys.exit(0)

    search_width: float = 10.
    seek_options = SeekOptions(input_media.video[0], start_time=likely_location-search_width, end_time=likely_location, mode="course")
    seek_options.calibrate(method="ffmpeg", device=device)

    black_gaps = find_black(
        seek_options)

    prior_black = None
    min_diff = float('inf')
    for bg in black_gaps:
        t = bg.end
        if t < likely_location:
            diff = likely_location - t
            if diff < min_diff:
                min_diff = diff
                prior_black = t

    if prior_black is None:
        print(f"No prior black frame found before {likely_location:.2f} seconds.")
    else:
        print(f"The prior black frame is at: {prior_black:.2f} seconds -> {to_timecode(prior_black)}")
