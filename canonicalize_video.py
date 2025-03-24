#!/usr/bin/env python3
import argparse
import subprocess
import os
from pymediainfo import MediaInfo


def get_media_info(file_path):
    """
    Use pymediainfo to extract media tracks from the input file.
    Returns lists for video, audio, and subtitle (text) tracks.
    """
    media_info = MediaInfo.parse(file_path)
    video_streams = []
    audio_streams = []
    subtitle_streams = []
    for track in media_info.tracks:
        if track.track_type == 'Video':
            video_streams.append(track)
        elif track.track_type == 'Audio':
            audio_streams.append(track)
        elif track.track_type == 'Text':
            subtitle_streams.append(track)
    return video_streams, audio_streams, subtitle_streams


def reorder_audio_streams(audio_streams):
    """
    Reorder audio streams so that if an English stream exists,
    it appears first.
    """
    english = []
    others = []
    for stream in audio_streams:
        lang = (getattr(stream, 'language', '') or '').lower()
        if lang.startswith("eng") or lang == "english":
            english.append(stream)
        else:
            others.append(stream)
    return english + others


def reorder_subtitle_streams(subtitle_streams):
    """
    Reorder subtitle streams so that English appears first.
    """
    english = []
    others = []
    for stream in subtitle_streams:
        lang = (getattr(stream, 'language', '') or '').lower()
        if lang.startswith("eng") or lang == "english":
            english.append(stream)
        else:
            others.append(stream)
    return english + others


def parse_bitrate(bitrate_str):
    """
    Parse bitrate string like '1500k' into an integer (bps).
    """
    if bitrate_str.endswith('k'):
        return int(bitrate_str[:-1]) * 1000
    return int(bitrate_str)


def compute_resolution(primary_video, target_vertical, default_resolution):
    """
    Compute the horizontal resolution while preserving the source's aspect ratio.
    Do not upscale: if the source's vertical resolution is lower than the target,
    return the native resolution.
    """
    try:
        orig_width = int(primary_video.width)
        orig_height = int(primary_video.height)
        if orig_height < target_vertical:
            # Do not upscale; use the original resolution.
            return f"{orig_width}x{orig_height}"
        aspect_ratio = orig_width / orig_height
        new_width = round(aspect_ratio * target_vertical)
        # Ensure width is even.
        if new_width % 2 != 0:
            new_width += 1
        return f"{new_width}x{target_vertical}"
    except (ValueError, TypeError, AttributeError):
        return default_resolution


def construct_ffmpeg_command(input_file, output_file, profile, audio_streams, subtitle_files, primary_video):
    """
    Build an ffmpeg command for transcoding the media file based on the chosen profile,
    taking into account the input video’s native resolution, bitrate, and codec.
    """
    # Define profile-specific target vertical resolutions and bitrate settings.
    if profile == '480p':
        target_vertical = 480
        default_resolution = '854x480'
        video_bitrate = '1500k'
        maxrate = '1500k'
        default_audio_channels = 2
    elif profile == '720p':
        target_vertical = 720
        default_resolution = '1280x720'
        video_bitrate = '3000k'
        maxrate = '3000k'
        default_audio_channels = 2
    elif profile == '1080p':
        target_vertical = 1080
        default_resolution = '1920x1080'
        video_bitrate = '15000k'
        maxrate = '15000k'
        default_audio_channels = 6 if any(
            getattr(a, 'channel_s', 2) >= 6 for a in audio_streams if hasattr(a, 'channel_s')
        ) else 2
    elif profile == '4K':
        target_vertical = 2160  # UHD vertical resolution
        default_resolution = '3840x2160'
        video_bitrate = '35000k'
        maxrate = '35000k'
        default_audio_channels = 6 if any(
            getattr(a, 'channel_s', 2) >= 6 for a in audio_streams if hasattr(a, 'channel_s')
        ) else 2
    else:
        raise ValueError("Unknown profile specified")
    
    # Decide on the final video resolution.
    resolution = compute_resolution(primary_video, target_vertical, default_resolution)

    # Determine if video transcoding is needed.
    # Conditions for direct copy:
    #   1. Input video codec is H.264.
    #   2. Input bitrate is available and is <= profile target bitrate.
    #   3. No scaling is needed (i.e. input vertical resolution is <= target_vertical).
    transcode_video = True  # default to transcoding
    try:
        input_codec = (primary_video.format or "").lower()
        input_bitrate = int(primary_video.bit_rate) if primary_video.bit_rate else None
        native_height = int(primary_video.height)
        target_bitrate_val = parse_bitrate(video_bitrate)
        if native_height <= target_vertical and "avc" in input_codec or "h264" in input_codec:
            if input_bitrate is not None and input_bitrate <= target_bitrate_val:
                transcode_video = False
    except (ValueError, TypeError, AttributeError):
        pass

    # Begin constructing the ffmpeg command.
    cmd = ['ffmpeg', '-y', '-i', input_file]

    # Add external subtitle files if specified.
    if subtitle_files:
        for sub in subtitle_files:
            if os.path.exists(sub):
                cmd.extend(['-i', sub])
            else:
                print(f"Warning: Subtitle file {sub} not found.")

    # Map primary video stream (assumed input index 0).
    cmd.extend(['-map', '0:v:0'])
    # Map audio streams (reordered so English is first).
    for idx in range(len(audio_streams)):
        cmd.extend(['-map', f'0:a:{idx}'])
    # If no external subtitles, map internal subtitles.
    if not subtitle_files:
        internal_subs = reorder_subtitle_streams([])
        for idx in range(len(internal_subs)):
            cmd.extend(['-map', f'0:s:{idx}'])

    # Video options: decide whether to copy or transcode.
    if transcode_video:
        # Use libx264 with scaling if needed.
        video_options = [
            '-c:v', 'libx264',
            '-b:v', video_bitrate,
            '-maxrate', maxrate,
            '-vf', f'scale={resolution}',
            '-r', '24'
        ]
    else:
        # Copy the video stream as-is.
        video_options = ['-c:v', 'copy']
    cmd.extend(video_options)

    # Audio encoding options (always re-encode audio to ensure proper channels).
    cmd.extend([
        '-c:a', 'aac',
        '-ac', str(default_audio_channels)
    ])

    # Handle subtitle streams if external files were provided.
    if subtitle_files:
        for sub_index in range(len(subtitle_files)):
            # External subtitle inputs start at index 1.
            cmd.extend(['-map', f'{sub_index+1}:0'])
        cmd.extend(['-c:s', 'mov_text'])

    # Set output container (MP4).
    cmd.append(output_file)
    return cmd


def main():
    parser = argparse.ArgumentParser(
        description="Canonicalize media file to a standard MP4 format with specific profiles, form factor adjustments, and conditional video copying."
    )
    parser.add_argument("input", help="Input media file")
    parser.add_argument("output", help="Output media file")
    parser.add_argument(
        "--profile",
        choices=['480p', '720p', '1080p', '4K'],
        default='1080p',
        help="Video profile to use (default: 1080p)"
    )
    parser.add_argument(
        "--subtitle-files",
        nargs="*",
        help="Optional subtitle files to include if internal subtitles are missing"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Optional dry run which only prints the transcoder call and doesn't run anything"
    )
    args = parser.parse_args()

    # Extract media info.
    video_streams, audio_streams, subtitle_streams = get_media_info(args.input)
    print(f"Found {len(video_streams)} video stream(s), {len(audio_streams)} audio stream(s), and {len(subtitle_streams)} subtitle stream(s).")

    # Reorder audio streams so English comes first.
    audio_streams = reorder_audio_streams(audio_streams)

    # Use the primary video stream for form factor and bitrate decisions.
    primary_video = video_streams[0] if video_streams else None

    if primary_video is None:
        print("Error: No video stream found in the input file.")
        return

    # Build and display the ffmpeg command.
    ffmpeg_cmd = construct_ffmpeg_command(args.input, args.output, args.profile, audio_streams, args.subtitle_files, primary_video)
    if not args.dry_run:
        print("Would run ffmpeg command:")
    else:
        print("Running ffmpeg command:")
    print(" ".join(ffmpeg_cmd))

    # Execute the ffmpeg command.
    if not args.dry_run:
        subprocess.run(ffmpeg_cmd)


if __name__ == "__main__":
    main()
