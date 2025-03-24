#!/usr/bin/env python3
import argparse
import subprocess
import os
from pymediainfo import MediaInfo


def get_media_info(file_path):
    """
    Extract media tracks using pymediainfo.
    Returns lists for video, audio, and subtitle tracks.
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
    Reorder audio streams so that English streams appear first.
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
    Convert bitrate string like '1500k' into an integer (in bps).
    """
    if bitrate_str.endswith('k'):
        return int(bitrate_str[:-1]) * 1000
    return int(bitrate_str)


def compute_resolution(primary_video, target_vertical, default_resolution):
    """
    Compute horizontal resolution preserving the aspect ratio.
    Do not upscale: if the source's vertical resolution is lower than the target,
    return the native resolution.
    """
    try:
        orig_width = int(primary_video.width)
        orig_height = int(primary_video.height)
        if orig_height < target_vertical:
            return f"{orig_width}x{orig_height}"
        aspect_ratio = orig_width / orig_height
        new_width = round(aspect_ratio * target_vertical)
        if new_width % 2 != 0:
            new_width += 1
        return f"{new_width}x{target_vertical}"
    except (ValueError, TypeError, AttributeError):
        return default_resolution


def construct_ffmpeg_command(input_file, output_file, profile, audio_streams, subtitle_files, primary_video):
    """
    Build an ffmpeg command for transcoding based on:
     - Desired output profile and target vertical resolution.
     - Codec decisions: 480p/720p/1080p use H.264, 4K uses HEVC.
     - For 4K, if the input is 10-bit then use a HEVC profile supporting 10-bit.
     - Avoid upscaling and re-encode only if necessary.
    """
    # Define target parameters per profile.
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
        # Use 6 channels if any audio stream indicates 5.1, else fallback to 2.
        default_audio_channels = 6 if any(
            getattr(a, 'channel_s', 2) >= 6 for a in audio_streams if hasattr(a, 'channel_s')
        ) else 2
    elif profile == '4K':
        target_vertical = 2160  # UHD vertical resolution (2160p)
        default_resolution = '3840x2160'
        video_bitrate = '35000k'
        maxrate = '35000k'
        default_audio_channels = 6 if any(
            getattr(a, 'channel_s', 2) >= 6 for a in audio_streams if hasattr(a, 'channel_s')
        ) else 2
    else:
        raise ValueError("Unknown profile specified")

    # Decide on desired codec.
    # For 4K, we want to use HEVC; for other profiles, use H.264.
    if profile == '4K':
        desired_codec = 'hevc'
    else:
        desired_codec = 'h264'

    # Compute the final resolution.
    resolution = compute_resolution(primary_video, target_vertical, default_resolution)

    # Determine if input is 10-bit (if available).
    is_10bit = False
    try:
        bit_depth = int(primary_video.bit_depth)
        if bit_depth >= 10:
            is_10bit = True
    except (ValueError, TypeError, AttributeError):
        pass

    # Decide whether to re-encode the video stream.
    transcode_video = True
    try:
        input_codec = (primary_video.format or "").lower()
        input_bitrate = int(primary_video.bit_rate) if primary_video.bit_rate else None
        native_height = int(primary_video.height)
        target_bitrate_val = parse_bitrate(video_bitrate)
        if native_height <= target_vertical:
            if desired_codec == 'h264' and ("avc" in input_codec or "h264" in input_codec):
                if input_bitrate is not None and input_bitrate <= target_bitrate_val:
                    transcode_video = False
            elif desired_codec == 'hevc' and ("hevc" in input_codec or "h265" in input_codec):
                if input_bitrate is not None and input_bitrate <= target_bitrate_val:
                    transcode_video = False
    except (ValueError, TypeError, AttributeError):
        pass

    # Begin constructing the ffmpeg command.
    cmd = ['ffmpeg', '-y', '-i', input_file]

    # Add external subtitle files if provided.
    if subtitle_files:
        for sub in subtitle_files:
            if os.path.exists(sub):
                cmd.extend(['-i', sub])
            else:
                print(f"Warning: Subtitle file {sub} not found.")

    # Map the primary video stream.
    cmd.extend(['-map', '0:v:0'])
    # Map audio streams (with English streams reordered).
    for idx in range(len(audio_streams)):
        cmd.extend(['-map', f'0:a:{idx}'])
    # Map internal subtitles if no external files are provided.
    if not subtitle_files:
        internal_subs = reorder_subtitle_streams([])
        for idx in range(len(internal_subs)):
            cmd.extend(['-map', f'0:s:{idx}'])

    # Video encoding options.
    if transcode_video:
        if desired_codec == 'h264':
            # Use libx264.
            video_options = ['-c:v', 'libx264', '-b:v', video_bitrate, '-maxrate', maxrate,
                             '-vf', f'scale={resolution}', '-r', '24']
            # For 1080p, set the high profile.
            if profile == '1080p':
                video_options.extend(['-profile:v', 'high'])
            # Optionally, for 480p and 720p you might choose 'main' or 'baseline'.
        elif desired_codec == 'hevc':
            # Use libx265.
            video_options = ['-c:v', 'libx265', '-b:v', video_bitrate, '-maxrate', maxrate,
                             '-vf', f'scale={resolution}', '-r', '24']
            # Choose the appropriate HEVC profile.
            if is_10bit:
                video_options.extend(['-profile:v', 'main10'])
            else:
                video_options.extend(['-profile:v', 'main'])
    else:
        # If conditions are met, copy the video stream.
        video_options = ['-c:v', 'copy']
    cmd.extend(video_options)

    # Audio encoding: always re-encode audio to ensure proper channel count.
    cmd.extend(['-c:a', 'aac', '-ac', str(default_audio_channels)])

    # Handle subtitles if external files are provided.
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
        description="Canonicalize media file to a standard MP4 format with profile-based codec and resolution handling."
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
        help="Optional subtitle files if internal subtitles are missing"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Specify whether to run or just report the ffmpeg command."
    )
    args = parser.parse_args()

    # Extract media info.
    video_streams, audio_streams, subtitle_streams = get_media_info(args.input)
    print(f"Found {len(video_streams)} video stream(s), {len(audio_streams)} audio stream(s), and {len(subtitle_streams)} subtitle stream(s).")

    ic(video_streams, audio_streams, subtitle_streams)

    # Reorder audio streams so that English appears first.
    audio_streams = reorder_audio_streams(audio_streams)

    # Use the primary video stream for resolution, bitrate, and codec decisions.
    primary_video = video_streams[0] if video_streams else None
    if primary_video is None:
        print("Error: No video stream found in the input file.")
        return

    # Build and display the ffmpeg command.
    ffmpeg_cmd = construct_ffmpeg_command(args.input, args.output, args.profile, audio_streams, args.subtitle_files, primary_video)
    if args.dry_run:
        print("Would run ffmpeg command:")
    else:
        print("Running ffmpeg command:")
    print(" ".join(ffmpeg_cmd))

    # Execute the ffmpeg command.
    if not args.dry_run:
        subprocess.run(ffmpeg_cmd)


if __name__ == "__main__":
    from mk_ic import install
    install()
    main()
