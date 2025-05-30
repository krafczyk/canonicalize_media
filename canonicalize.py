import argparse
from av_info.session import VideoStream, Session
from av_info.utils import version_tuple, ask_continue
from av_info.omdb import query
from av_info.plex import build_media_path, guess_omdb_from_path
from typing import cast
import subprocess
import json
import os
import sys
from pprint import pprint


acceptable_subtitle_codecs = ['subrip', 'mov_text', 'hdmv_pgs_subtitle', 'dvd_subtitle']


width_map: dict[str, tuple[int,...]] = {
    "480p": (720,),
    "720p": (1280,),
    "1080p": (1920,),
    "4K": (3840, 4096)
}


def is_res_match(width: int, target_res_widths: tuple[int,...]) -> bool:
    """Compare the width of a video stream to the target resolution widths."""
    is_match: bool = False
    err: float = 0.01
    for t_width in target_res_widths:
        if (float(abs(width - t_width))/t_width) < err:
            is_match = True
            break
    return is_match


max_bitrate_map: dict[str, int] = {
    "480p": 1500,
    "720p": 3000,
    "1080p": 15000,
    "4K": 35000
}


# Video decoder limitations
#H.264 FHD: Level 4.1 supported (FMO/ASO/RS not supported).
#H.264 UHD: Level 5.1 supported, seamless resolution change supported up to 3840x2160.
#HEVC FHD: Level 4.1 supported.
#HEVC UHD: Level 5.1 supported, seamless resolution change supported up to 3840x2160
#HEVC: Supported only for MKV/MP4/TS containers

supported_codecs = [
    "h264",
    "avc1", # another name for h264
    "AVC",
    "hevc",
    "HEVC",
]


def build_video_codec_args(vid: VideoStream, target_res: str, force: bool=False) -> list[str]:
    if not is_res_match(vid.width, width_map[target_res]) and not force:
        raise ValueError(f"Video resolution {vid.width} doesn't match target resolution {target_res}.")

    # Check if we need to lower bitrate
    reduce_quality = False
    if vid.bit_rate > max_bitrate_map[target_res]:
        reduce_quality = True

    # Check if we need to change codec
    change_codec = False
    if vid.codec not in supported_codecs:
        change_codec = True

    # If we don't need to change codec, check that the stream is using the right level
    change_level = False
    max_level = "5.1" if target_res in ("4K", "1080p") else "4.1"
    # Compare codec level using version number comparison
    if version_tuple(vid.level) > version_tuple(max_level):
        change_level = True

    if not (reduce_quality or change_codec or change_level):
        print(f"Video can be copied without transcoding.")
        return [ "-c:v", "copy" ]
    else:
        # We must transcode.
        print(f"Video must be transcoded:")
        if reduce_quality:
            print(f"  Quality reduction needed. Target bitrate: {max_bitrate_map[target_res]}k, Video bitrate: {vid.bit_rate}k")
        if change_codec:
            print(f"  Codec change needed. Video codec: {vid.codec}")
        if change_level:
            print(f"  Encoding level change needed. max level: {max_level}, Video level: {vid.level}")

        # Prefer hevc
        transcode_options: list[str] = []
        target_codec = "hevc" if change_codec else vid.codec
        if target_codec == "hevc":
            target_codec = "hevc_nvenc"
        transcode_options += [ "-c:v", target_codec ]
 
        # Set bitrate limit
        max_bitrate = min(max_bitrate_map[target_res], vid.bit_rate)
        transcode_options += [
            "-maxrate",
            f"{max_bitrate}k",
            "-bufsize",
            f"{2*max_bitrate}k"
        ]

        # Check that hdr files are using hevc
        if vid.bit_depth == 10:
            if target_codec != "hevc":
                raise ValueError("HDR files must be transcoded to HEVC.")

        # Set profile/level
        if target_codec == "h264":
            if vid.codec == target_codec:
                # Use the same profile/level as the original
                transcode_options += [ "-profile:v", vid.profile ]
            else:
                transcode_options += [ "-profile:v", "high" ]

            if target_res in ("480p", "720p", "1080p"):
                transcode_options += [ "-level:v", "4.1" ]
            else:
                transcode_options += [ "-level:v", "5.1" ]

        elif target_codec in ("hevc", "libx265"):
            if vid.codec == target_codec:
                # Use the same profile/level as the original
                transcode_options += [ "-profile:v", vid.profile ]
            else:
                if vid.bit_depth == 10:
                    transcode_options += [ "-profile:v", "main10" ]
                else:
                    transcode_options += [ "-profile:v", "main" ]

            if target_res in ("480p", "720p", "1080p"):
                if target_codec == "libx265":
                    transcode_options += [ "-x265-params", "level-idc=4.1" ]
                else:
                    transcode_options += [ "-level:v", "4.1" ]
            else:
                if target_codec == "libx265":
                    transcode_options += [ "-x265-params", "level-idc=5.1" ]
                else:
                    transcode_options += [ "-level:v", "5.1" ]

        if target_codec == "hevc_nvenc":
            transcode_options += [ "-preset", "slow", "-cq", "22", "-rc", "vbr", "-tune", "hq" ]
        else:
            transcode_options += [ "-preset", "slow", "-crf", "22"]

        return transcode_options



if __name__ == "__main__":
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    # An input argument that takes a list of filepaths
    _ = parser.add_argument("--input", "-i", nargs="+", action="extend", help="Input file(s), format is <filename>@@<Title>@@<Language> where the two extra fields are only relevant for extra audio/subtitle tracks.", required=True)
    _ = parser.add_argument("--output", "-o", help="The output file to write to.")
    _ = parser.add_argument("--imdb-id", help="The imdb id of this movie or show. It will be used to build the output filename if --title is not specified.", type=str, required=False)
    _ = parser.add_argument("--title", "-t", help="The title of the movie to use")
    _ = parser.add_argument("--res", "-r", help="The resolution category to use")
    _ = parser.add_argument("--edition", "-e", help="Special 'editions' such as 'Extended'")
    _ = parser.add_argument("--yes", help="Don't prompt user for confirmation.", action="store_true")
    _ = parser.add_argument("--info", help="Activate info mode similar to calling ffprobe or mediainfo", action="store_true")
    _ = parser.add_argument("--copy-video", help="Copy the video stream. Skip Heuristic/Transcoding", action="store_true")
    _ = parser.add_argument("--dry-run", help="Only construct the command, do not run it.", action="store_true")
    args = parser.parse_args()

    inputs: list[str] = cast(list[str], args.input)

    session = Session(inputs)

    if cast(bool,args.info):
        print(f"Stream Summary:")
        for vid_stream in session.video_streams:
            pprint(vid_stream)
        for aud_stream in session.audio_streams:
            pprint(aud_stream)
        for sub_stream in session.subtitle_streams:
            pprint(sub_stream)
        sys.exit(0)

    if len(session.video_streams) == 0:
        raise ValueError("No video streams found.")
    if len(session.video_streams) > 1:
        raise ValueError("Only one video stream is supported!")

    args_res: str | None = cast(str | None, args.res)
    force_res: bool = False
    if args_res is not None:
        force_res = True
    res: str
    if args_res is None:
        # Guess resolution from video stream
        vid_width = session.video_streams[0].width
        target_res: str|None = None
        for res_name, widths in width_map.items():
            if is_res_match(vid_width, widths):
                target_res = res_name
                break

        if target_res is None:
            raise ValueError(f"Video resolution {vid_width} didn't match any known resolution")
        print(f"Video resolution {vid_width} matched target resolution {target_res}.")
        res = target_res
    else:
        if args_res not in ["480p", "720p", "1080p", "4K"]:
            raise ValueError("Resolution must be one of 480p, 720p, 1080p, or 4K.")
        res = args_res

    output_filepath: str
    args_output: str | None = cast(str | None, args.output)
    imdb_id: str | None = cast(str | None, args.imdb_id)
    title: str | None = cast(str |None, args.title)
    output_set_manually:bool = False
    if args_output is None:
        if imdb_id is not None:
            if title is not None:
                raise ValueError("Cannot specify both --imdb-id and --title.")
            omdb_res = query(imdb_id=imdb_id)
            if not omdb_res:
                raise ValueError(f"Could not find movie with IMDB id {imdb_id}.")
            output_filepath = str(build_media_path(
                omdb_res,
                ext="mp4",
                resolution=res, 
                edition=cast(str | None, args.edition)))
        else:
            # Guess IMDB id from the first video stream
            omdb_res = guess_omdb_from_path(session.video_streams[0].filepath)
            if not omdb_res:
                raise ValueError(f"Could not find movie with IMDB id {imdb_id}.")
            title = omdb_res.get('Title', None)
            print(f"Found match. [{omdb_res['Title']} ({omdb_res['Year']})] imdb_id: [{omdb_res['imdbID']}]")
            output_filepath = str(build_media_path(
                omdb_res,
                ext="mp4",
                resolution=res, 
                edition=cast(str | None, args.edition)))

    else:
        output_filepath = args_output
        output_set_manually = True

    if not cast(bool,args.yes) or not output_set_manually:
        if not ask_continue("Proceed with output file: " + output_filepath + "?"):
            print("Aborting.")
            exit(1)

    # Make output directory
    os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

    # Some circumstances require mkv
    mkv_needed = False

    # Build ffmpeg command
    ffmpeg_cmd = [ "ffmpeg", "-hide_banner"]
    # Add input files
    for inp in inputs:
        ffmpeg_cmd += ["-i", inp ]

    ffmpeg_cmd += [ "-metadata", f"title={title}" ] if title else []

    # Selected video stream
    vid_cont = session.filename_cont_map[session.video_streams[0].filepath]
    stream_id = vid_cont.idx
    ffmpeg_cmd += [ "-map", f"{stream_id}:0" ]

    if vid_cont.menu:
        ffmpeg_cmd += [ "-map_chapters", "0"]

    ffmpeg_cmd += [ "-map_metadata", "0"]

    # Specify video encoder
    copy_video: bool = cast(bool, args.copy_video)
    if copy_video:
        ffmpeg_cmd += [ "-c:v", "copy" ]
    else:
        ffmpeg_cmd += build_video_codec_args(session.video_streams[0], res, force_res)

    # Sort audio streams english streams first, 5.1 first
    audio_streams_sorted = sorted(session.audio_streams, key=lambda x: (x.language != "eng" and x.language != "en", x.channels != 6))

    for a_stream in audio_streams_sorted:
        stream_id = session.filename_cont_map[a_stream.filepath].idx
        ffmpeg_cmd += [ "-map", f"{stream_id}:{a_stream.idx}" ]

    # Specify audio encoder
    ffmpeg_cmd += [ "-c:a", "copy" ]

    # crash if we have an unsupported codec.
    for s_stream in session.subtitle_streams:
        if s_stream.codec == "hdmv_pgs_subtitle":
            mkv_needed = True
        if s_stream.codec == "dvd_subtitle":
            mkv_needed = True
        if s_stream.codec not in acceptable_subtitle_codecs:
            raise ValueError(f"Subtitle codec {s_stream.codec} is not supported!")

    # Sort subtitle streams english streams first
    subtitle_streams_sorted = sorted(session.subtitle_streams, key=lambda x: (x.language != "eng", acceptable_subtitle_codecs.index(x.codec)))

    s_idx = 0
    for s_stream in subtitle_streams_sorted:
        stream_id = session.filename_cont_map[s_stream.filepath].idx
        ffmpeg_cmd += [ "-map", f"{stream_id}:{s_stream.idx}" ]
        if s_stream.codec == "hdmv_pgs_subtitle":
            ffmpeg_cmd += [ f"-c:s:{s_idx}", "copy" ]
        if s_stream.codec == "dvd_subtitle":
            ffmpeg_cmd += [ f"-c:s:{s_idx}", "copy" ]
        else:
            # Otherwise try to convert to mov_text
            if not mkv_needed and s_stream.codec != "mov_text":
                ffmpeg_cmd += [ f"-c:s:{s_idx}", "mov_text" ]
            else:
                ffmpeg_cmd += [ f"-c:s:{s_idx}", "copy" ]
        if s_stream.language != "und":
            ffmpeg_cmd += [ f"-metadata:s:s:{s_idx}", f"language={s_stream.language}" ]
        if s_stream.title != "":
            ffmpeg_cmd += [ f"-metadata:s:s:{s_idx}", f"title={s_stream.title}" ]
        s_idx += 1

    # Set default streams
    ffmpeg_cmd += [
        "-disposition:a:0", "default",
    ]
    if len(subtitle_streams_sorted) > 0:
        ffmpeg_cmd += [
            "-disposition:s:0", "default",
        ]

    # Add output file
    if mkv_needed and ('mp4' in output_filepath):
        if output_set_manually:
            raise ValueError("Output file must be .mkv if subtitles are in hdmv_pgs_subtitle format.")
        output_filepath = output_filepath.replace(".mp4", ".mkv")

    ffmpeg_cmd += [ f"file:{output_filepath}" ]

    # Print the command
    print("ffmpeg command:")
    print(" ".join(ffmpeg_cmd))

    # Run the command
    if not cast(bool, args.dry_run):
        _ = subprocess.run(ffmpeg_cmd, capture_output=False, check=True)

        # Write metadata about input files
        metadata = {
            "input_files": inputs,
            "ffmpeg_cmd": " ".join(ffmpeg_cmd),
        }

        # replace the extension with .json
        metadata_filepath = output_filepath.split(".")[0]+".json"
        with open(metadata_filepath, "w") as f:
            _ = f.write(json.dumps(metadata, indent=4))
