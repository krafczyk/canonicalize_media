import argparse
from typing import cast
from av_info.session import MediaContainer
from av_info.ffmpeg_ops import get_keyframe_times, find_image, SeekOptions, reencode, to_timecode
from av_info.utils import get_device, die
import re
import sys
import os


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
    _ = parser.add_argument("--device", help="Specify a device", type=int, required=False)
    _ = parser.add_argument("--mode", help="Change behavior", default="best")
    args = parser.parse_args()

    image_path=cast(str,args.image)
    video_file=cast(str,args.video)
    search_start=cast(str, args.search_start)
    arg_search_end = cast(str|None, args.search_end)

    video_basename = os.path.basename(video_file)

    # Check extension. It should be .mkv
    if not video_basename.endswith('.mkv'):
        raise ValueError("Video file must have a .mkv extension.")


    # Expect: Show Name (Year) - SXXEYY-EZZ - TitleY & TitleZ (…metadata…)
    ep_pattern = re.compile(r'(.+) - (S[0-9]{2}E[0-9]{2}-E[0-9]{2}) - (.+) & (.+) (\(.*\))')
    m = ep_pattern.match(video_basename)
    if not m:
        die("filename does not match expected pattern.")
        sys.exit(1)

    show, ep_range, title1, title2, metadata = m.groups()

    # Extract season & episode numbers from ep_range like "S03E06-E07"
    ep_pattern = re.compile(r'S([0-9]{2})E([0-9]{2})-E([0-9]{2})')
    m2 = ep_pattern.match(ep_range)
    if not m2:
        die("episode range doesn’t match SXXEYY-EZZ format.")
        sys.exit(1)

    season, ep1, ep2 = m2.groups()

    show, ep_range, title1, title2, metadata = m.groups()

    input_media = MediaContainer(video_file)
    input_media.analyze()

    device = cast(int|None, args.device)

    seek_options = SeekOptions(input_media.video[0], search_start, arg_search_end, mode="course") 
    seek_options.calibrate(method="ffmpeg", device=device, verbose=True)

    im_location = find_image(
        seek_options,
        image_path,
        device=device,
        mode=cast(str, args.mode),
        verbose=True)

    if im_location < 0.:
        print("Image not found in the video.")
        sys.exit(1)

    ic(im_location)

    first_code = f"S{season}E{ep1}"
    second_code = f"S{season}E{ep2}"

    output_dir = os.path.dirname(video_file)

    # Rename the split files
    new_name1 = f"{show} - {first_code} - {title1} {metadata}.mkv"
    reencode(input_media, os.path.join(output_dir, new_name1), end=to_timecode(im_location-0.1), verbose=True)

    new_name2 = f"{show} - {second_code} - {title2} {metadata}.mkv"
    reencode(input_media, os.path.join(output_dir, new_name2), start=to_timecode(im_location+0.1), verbose=True)

    # Summary output
    print("Done! Created:")
    print(f"  • {new_name1}")
    print(f"  • {new_name2}")
