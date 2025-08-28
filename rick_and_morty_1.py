import argparse
from typing import cast
import subprocess
from av_info import MediaContainer

if __name__ == "__main__":

    parser = argparse.ArgumentParser("Rick and Morty Combine")
    _ = parser.add_argument(
        "--inputs",
        help="Path to the input files.",
        nargs="+"
    )
    _ = parser.add_argument(
        "--output",
        help="Path to the output file.",
        required=False,
        default="output.mkv"
    )
    _ = parser.add_argument(
        "--dry-run",
        help="If set, don't actually run ffmpeg, just print the command that would be run.",
        action="store_true",)
    args = parser.parse_args()

    inputs = cast(list[str], args.inputs)
    output = cast(str, args.output)
    dry_run = cast(bool, args.dry_run)

    if len(inputs) < 2:
        raise ValueError("At least two input files are required.")

    if len(inputs) > 2:
        raise ValueError("Only two input files are supported.")

    filepath_a = inputs[0]
    filepath_b = inputs[1]

    cont_a = MediaContainer(filepath_a)
    cont_a.analyze()

    cont_b = MediaContainer(filepath_b)
    cont_b.analyze()

    candidate_streams = [cont_a.video[0], cont_b.video[0]]

    # Only pick streams that are 1920 wide or wider
    candidate_streams = list(filter(lambda v: v.width >= 1920, candidate_streams))

    # Are there any 10bit streams?
    if any(map(lambda v: v.bit_depth == 10, candidate_streams)):
        # Prune streams that aren't 10bit
        candidate_streams = list(filter(lambda v: v.bit_depth == 10, candidate_streams))

    # Sort streams by bit_rate
    candidate_streams.sort(key=lambda v: v.bit_rate or 0, reverse=True)

    # Select the highest bit_rate stream
    video_stream = candidate_streams[0]


    candidate_streams = [cont_a.audio[0], cont_b.audio[0]]

    # Heuristics to pick the best audio stream

    # Are there any 6 channel tracks?
    if any(map(lambda a: a.channels >= 6, candidate_streams)):
        # Prune streams that have < 6 channels
        candidate_streams = list(filter(lambda a: a.channels >= 6, candidate_streams))

    # Are there any explicitly english trcks?
    if any(map(lambda a: a.language == 'en', candidate_streams)):
        # Prune streams that aren't explicitly 'english'
        candidate_streams = list(filter(lambda a: a.language == 'en', candidate_streams))

    if len(candidate_streams) == 0:
        raise ValueError("No candidate audio streams found.")

    # Sort streams by bit_rate
    candidate_streams.sort(key=lambda a: a.bit_rate or 0, reverse=True)

    # Select the highest bit_rate stream
    audio_stream = candidate_streams[0]

    input_filepaths = [filepath_a, filepath_b]

    menu_args = []
    video_args = []
    for i, f_p in enumerate(input_filepaths):
        if f_p == video_stream.filepath:
            video_args = [ "-map", f"{i}:{video_stream.idx}", "-c:v", "copy" ]
    if len(video_args) == 0:
        raise ValueError("Video stream filepath not found in inputs.")

    audio_args = []
    for i, f_p in enumerate(input_filepaths):
        if f_p == audio_stream.filepath:
            audio_args = [ "-map", f"{i}:{audio_stream.idx}", "-c:a", "copy" ]
    if len(audio_args) == 0:
        raise ValueError("Audio stream filepath not found in inputs.")

    subtitle_args = []
    if len(cont_a.subtitle) > 0:
        subtitle_args += [ "-map", f"0:{cont_a.subtitle[0].idx}", "-c:s", "copy" ]
    if len(cont_b.subtitle) > 0:
        subtitle_args += [ "-map", f"1:{cont_b.subtitle[0].idx}", "-c:s", "copy" ]

    menu_args = []
    if cont_a.menu:
        menu_args += [ "-map_chapters", "0" ]
    elif cont_b.menu:
        menu_args += [ "-map_chapters", "1" ]

    # Build ffmpeg command
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-i", filepath_a,
        "-i", filepath_b,
        *video_args,
        *audio_args,
        *subtitle_args,
        *menu_args,
        output
    ]
    if dry_run:
        print(f"{' '.join(cmd)}")
    else:
        subprocess.run(cmd, check=True)
