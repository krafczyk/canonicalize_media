import argparse
from typing import cast
from av_info.session import MediaContainer
from av_info.ffmpeg_ops import get_keyframe_times, find_input_file_arg, find_image
import os


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Locate an image in a video file using ffmpeg."
    )
    _ = parser.add_argument("image", help="Path to the image to locate", type=str)
    _ = parser.add_argument("ffmpeg_args", help="Arguments to pass to ffmpeg", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    image_path=cast(str,args.image)
    ffmpeg_args=cast(list[str], args.ffmpeg_args)

    input_file = find_input_file_arg(ffmpeg_args)
    if not input_file:
        raise ValueError("No input file specified. Use -i <input_file>.")

    input_media = MediaContainer(input_file)
    input_media.analyze()

    device = None
    if os.environ.get("CUDA_VISIBLE_DEVICES") is not None:
        device = int(os.environ["CUDA_VISIBLE_DEVICES"].split(",")[0])

    keyframes = get_keyframe_times(input_media.video[0])

    # find start_time preceeded by `-ss`
    start_time = 0.
    for i, arg in enumerate(ffmpeg_args):
        if arg == "-ss" and i + 1 < len(ffmpeg_args):
            start_time = ffmpeg_args[i + 1]
            break

    # find end_time preceeded by `-to`
    end_time = None
    for i, arg in enumerate(ffmpeg_args):
        if arg == "-to" and i + 1 < len(ffmpeg_args):
            end_time = ffmpeg_args[i + 1]
            break

    likely_location = find_image(
        input_media.video[0],
        image_path,
        start_time=start_time,
        end_time=end_time,
        keyframes=keyframes,
        device=device)

    print(f"The image is likely located at: {likely_location:.2f} seconds")
