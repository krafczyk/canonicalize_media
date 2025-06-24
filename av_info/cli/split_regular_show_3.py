import argparse
from typing import cast
from av_info.session import MediaContainer, create_black_png
from av_info.ffmpeg_ops import get_keyframe_times, find_image, SeekOptions, reencode, to_timecode, find_black, ssim_eval
from av_info.utils import die
import numpy as np
import re
import sys
import os


def main() -> None:
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser(
        description="Locate an image in a video file using ffmpeg."
    )
    _ = parser.add_argument("--title-image", help="Path to title example", type=str, required=True)
    _ = parser.add_argument("--ep-title-image", help="Path to episode title example", type=str, required=True)
    _ = parser.add_argument("--black-image", help="Path to black example", type=str, required=False)
    _ = parser.add_argument("--video", help="Path to the video file", type=str, required=True)
    _ = parser.add_argument("--search-start", help="start time", type=str, required=False)
    _ = parser.add_argument("--search-end", help="end time", type=str, required=False)
    _ = parser.add_argument("--ssim-thresh", help="threshold to accept an image exists", type=float, default="10.0")
    _ = parser.add_argument("--device", help="Specify a device", type=int, required=False)
    args = parser.parse_args()

    black_image=cast(str|None,args.black_image)
    title_image=cast(str,args.title_image)
    ep_title_image=cast(str,args.ep_title_image)
    video_file=cast(str,args.video)
    start=cast(str|None, args.search_start)
    end=cast(str|None, args.search_end)
    ssim_thresh= cast(float, args.ssim_thresh)
    device=cast(int|None, args.device)

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

    if not black_image:
        create_black_png(input_media.video[0], "black.png")

    device = cast(int|None, args.device)

    keyframes = get_keyframe_times(input_media.video[0])

    seek_options = SeekOptions(input_media.video[0], start, end, mode="course", keyframes=keyframes) 
    seek_options.calibrate(method="ffmpeg", device=device, verbose=True)

    df = ssim_eval(
        seek_options,
        [black_image, title_image, ep_title_image],
        columns=["black", "title", "ep_title"],
        device=device,
        verbose=True)

    df = df.dropna()

    # First, check the main title is present.
    if np.max(df['title']) >= ssim_thresh:
        print("Title card found.")
        s = df['title']-df['black']
        s_diff = s.diff()
        s_diff = s_diff[~s_diff.isna()]

        ts = df.loc[s_diff[s_diff == max(s_diff)].index[0].item()]['pts']
        split_location = ts/1000.
    else:
        print("Only episode card found.")
        s = df['ep_title']-df['black']
        s_diff = s.diff()
        s_diff = s_diff[~s_diff.isna()]

        ts = df.loc[s_diff[s_diff == max(s_diff)].index[0].item()]['pts']
        split_location = ts/1000.

    print(f"Split location: {to_timecode(split_location)}")

    first_code = f"S{season}E{ep1}"
    second_code = f"S{season}E{ep2}"

    output_dir = os.path.dirname(video_file)

    # Rename the split files
    new_name1 = f"{show} - {first_code} - {title1} {metadata}.mkv"
    reencode(input_media, os.path.join(output_dir, new_name1), end=to_timecode(split_location-0.1), verbose=True)

    new_name2 = f"{show} - {second_code} - {title2} {metadata}.mkv"
    reencode(input_media, os.path.join(output_dir, new_name2), start=to_timecode(split_location), verbose=True)

    # Summary output
    print("Done! Created:")
    print(f"  • {new_name1}")
    print(f"  • {new_name2}")


if __name__ == "__main__":
    main()
