import argparse
from av_info.session import BaseStream, VideoStream, SubtitleStream, Session
from av_info.utils import version_tuple, ask_continue
from av_info.db import get_provider
from av_info.plex import build_media_path, guess
from typing import cast
import subprocess
import json
import os
import sys
from pprint import pprint


acceptable_subtitle_codecs = ['subrip', 'mov_text', 'ass', 'hdmv_pgs_subtitle', 'dvd_subtitle']


width_map: dict[str, tuple[int,...]] = {
    "480p": (640,),
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



def main() -> None:
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    # An input argument that takes a list of filepaths
    _ = parser.add_argument("--input", "-i", nargs="+", action="extend", help="Input file(s), format is <filename>@@<Title>@@<Language> where the two extra fields are only relevant for extra audio/subtitle tracks.", required=True)
    _ = parser.add_argument("--staging-dir", help="Staging output directory to use.", type=str, required=False)
    _ = parser.add_argument("--output", "-o", help="The output file to write to.")
    _ = parser.add_argument("--uid", help="The unique id of this movie or show. It will be used to build the output filename if --title is not specified.", type=str, required=False)
    _ = parser.add_argument("--title", "-t", help="The title of the movie to use")
    _ = parser.add_argument("--year", help="Override year in some circumstances", type=str, required=False)
    _ = parser.add_argument("--series-uid", help="Override series entry in some circumstances", type=str, required=False)
    _ = parser.add_argument("--skip-if-exists", help="Skip processing if the output file already exists.", action="store_true")
    _ = parser.add_argument("--res", "-r", help="The resolution category to use")
    _ = parser.add_argument("--edition", "-e", help="Special 'editions' such as 'Extended'")
    _ = parser.add_argument("--yes", help="Don't prompt user for confirmation.", action="store_true")
    _ = parser.add_argument("--info", help="Activate info mode similar to calling ffprobe or mediainfo", action="store_true")
    _ = parser.add_argument("--convert-advanced-subtitles", help="Convert 'advanced' subtitle formats such as image based formats and .ass format.", action="store_true")
    _ = parser.add_argument("--copy-video", help="Copy the video stream. Skip Heuristic/Transcoding", action="store_true")
    _ = parser.add_argument("--metadata-provider", help="Metadat provider to use", default="omdb", type=str)
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
    year = cast(str | None, args.year)
    series_uid = cast(str | None, args.series_uid)
    uid: str | None = cast(str | None, args.uid)
    title: str | None = cast(str |None, args.title)
    provider = get_provider(cast(str,args.metadata_provider))

    if args_output is None:
        if uid is not None:
            if title is not None:
                raise ValueError("Cannot specify both --imdb-id and --title.")
            guessed_media = guess("", uid=uid, provider=provider)
            if not guessed_media:
                raise ValueError(f"Could not find movie with uid {uid}.")
            output_filepath = str(build_media_path(
                guessed_media,
                ext="mp4",
                resolution=res, 
                edition=cast(str | None, args.edition)))
        else:
            guessed_media = guess(
                session.video_streams[0].filepath,
                uid=uid,
                title=title,
                year=year,
                series_uid=series_uid,
                provider=provider)

            if not guessed_media:
                print(f"Could not guess with filepath {session.video_streams[0].filepath}.")
                sys.exit(1)

            #title = guessed_media.title
            title = guessed_media.fullname()
            print(f"Found match. [{guessed_media.title} ({guessed_media.year})] imdb_id: [{guessed_media.uid}]")
            output_filepath = str(build_media_path(
                guessed_media,
                ext="mp4",
                resolution=res, 
                edition=cast(str | None, args.edition)))

    else:
        output_filepath = args_output

    # Some circumstances require mkv
    mkv_needed = False

    # Build ffmpeg command
    ffmpeg_cmd: list[str] = [ "ffmpeg", "-hide_banner", "-y" ]

    input_args: list[str] = []
    output_args: list[str] = []

    file_idx_map: dict[str,int] = {}
    f_idx = 0

    def f_stream_process(s: BaseStream):
        nonlocal f_idx
        if s.filepath not in file_idx_map:
            file_idx_map[s.filepath] = f_idx
            f_idx += 1

    def get_f_idx(s: BaseStream) -> int:
        return file_idx_map[s.filepath]

    # Add video stream
    f_stream_process(session.video_streams[0])
    vid_stream_filepath = session.video_streams[0].filepath
    vid_cont = session.filename_cont_map[vid_stream_filepath]
    stream_id = session.video_streams[0].idx
    file_idx = get_f_idx(session.video_streams[0])
    output_args += [ "-map", f"{file_idx}:{stream_id}" ]

    # Specify video encoder
    copy_video: bool = cast(bool, args.copy_video)
    if copy_video:
        output_args += [ "-c:v", "copy" ]
    else:
        output_args += build_video_codec_args(session.video_streams[0], res, force_res)

    if len(session.video_streams) > 2:
        raise  ValueError("Only up to two video streams are currently supported!")

    elif len(session.video_streams) > 1:
        if session.video_streams[1].codec != "mjpeg":
            raise ValueError("Second video stream must be MJPEG")
        v_stream = session.video_streams[1]
        f_stream_process(v_stream)
        file_idx = get_f_idx(v_stream)
        stream_id = v_stream.idx
        output_args += [ "-map", f"{file_idx}:{stream_id}" ]
        output_args += [ "-c:v", "copy" ]

    # Sort audio streams english streams first, 5.1 first
    audio_streams_sorted = sorted(session.audio_streams, key=lambda x: x.channels != 6)

    for a_stream in audio_streams_sorted:
        f_stream_process(a_stream)
        file_idx = get_f_idx(a_stream)
        output_args += [ "-map", f"{file_idx}:{a_stream.idx}" ]

    # Specify audio encoder
    output_args += [ "-c:a", "copy" ]

    convert_subtitles: bool = cast(bool, args.convert_advanced_subtitles)

    # Pass 1: Detect MKV necessity
    for s_stream in session.subtitle_streams:
        if s_stream.codec == "hdmv_pgs_subtitle" or s_stream.format == "hdmv_pgs_subtitle":
            mkv_needed = True
        elif s_stream.codec == "dvd_subtitle" or s_stream.format == "dvd_subtitle":
            mkv_needed = True
        elif s_stream.codec == "ass":
            mkv_needed = True
        elif s_stream.codec not in acceptable_subtitle_codecs and s_stream.format not in acceptable_subtitle_codecs:
            raise ValueError(f"Subtitle codec {s_stream.codec} is not supported!")

    # Handling output directory now since we have enough information to modify the filetype
    # but before doing subtitle processing as some subtitles take a very long time to process.
    # Handle output file extension validation
    if mkv_needed and ('mp4' in output_filepath):
        output_filepath = output_filepath.replace(".mp4", ".mkv")

    # Add staging directory if specified
    staging_dir: str | None = cast(str | None, args.staging_dir)
    if staging_dir is not None:
        output_filepath = os.path.join(staging_dir, output_filepath)

    yes: bool = cast(bool, args.yes)
    skip_if_exists: bool = cast(bool, args.skip_if_exists)

    # Early user confirmation
    if not yes:
        if not ask_continue("Proceed with output file: " + output_filepath + "?"):
            print("Aborting.")
            exit(1)

    if os.path.exists(output_filepath):
        if skip_if_exists:
            print(f"Output file {output_filepath} already exists. Skipping.")
            exit(0)
        if not yes:
            if not ask_continue("Output file " + output_filepath + " exists, overwrite?"):
                print("Aborting.")
                exit(1)

    print(f"Writing output to {output_filepath}")

    # Make output directory
    os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

    # Pass 2: Build list of subtitles and target codecs

    # Build final list of subtitles with their target codecs, and conversion lists
    subtitle_map: list[tuple[SubtitleStream,str]] = []

    # Complex subtitle conversion
    initial_sub_list = session.subtitle_streams.copy()
    conv_id = 0
    def get_s_codec(s: SubtitleStream) -> str:
        return s.codec if s.codec != '[0][0][0][0]' else s.format

    for s_stream in initial_sub_list:
        s_codec = get_s_codec(s_stream)
        if s_codec == "hdmv_pgs_subtitle":
            subtitle_map.append((s_stream, s_codec))
            if convert_subtitles and s_stream.language in ("eng", "en"):
                # Convert PGS subtitles to SRT
                s_filename = s_stream.filepath
                srt_filename = f"{s_filename}.{conv_id}.srt"
                if not os.path.exists(srt_filename):
                    sup_filename = f"{s_filename}.{conv_id}.sup"
                    print(f"Encountered PGS subtitle stream [{s_stream.title}] ({s_stream.idx})...")
                    if not os.path.exists(sup_filename):
                        # Extract the PGS subtitle
                        print(f"Extracting to {sup_filename}")
                        sup_command = [
                            "ffmpeg", "-hide_banner",
                            "-i", s_stream.filepath,
                            "-map", f"0:{s_stream.idx}",
                            "-c:s", "copy",
                            f"file:{sup_filename}"]
                        out = subprocess.run(sup_command, capture_output=True)
                        if out.returncode != 0:
                            raise ValueError(f"Failed to extract PGS subtitle stream: {out.stderr.decode('utf-8')}")
                    # Convert to SRT
                    print(f"Converting to SRT")
                    out = subprocess.run([
                        "bash", "pgstosrt.sh", sup_filename
                        ], capture_output=True)
                    if out.returncode != 0:
                        raise ValueError(f"Failed to convert PGS subtitle to SRT: {out.stderr.decode('utf-8')}")
                    # Remove the original SUP file
                    os.remove(sup_filename)
                    if not os.path.exists(srt_filename):
                        raise ValueError(f"Failed to convert PGS subtitle to SRT: {srt_filename} does not exist.")
                # Add the new SRT file to the session
                srt_cont = session.add_file(srt_filename)
                # Set the subtitle stream properties
                f_stream_process(srt_cont.subtitle[0])
                srt_cont.subtitle[0].language = s_stream.language
                srt_cont.subtitle[0].title = f"{s_stream.title} (OCR)"
                subtitle_map.append((srt_cont.subtitle[0], get_s_codec(srt_cont.subtitle[0])))
                conv_id += 1
        elif s_codec == "dvd_subtitle":
            mkv_needed = True
            subtitle_map.append((s_stream, s_codec))
            if convert_subtitles and s_stream.language in ("eng", "en"):
                # Convert VobSub subtitles to SRT
                s_filename = s_stream.filepath
                srt_filename = f"{s_filename}.{conv_id}.srt"
                if not os.path.exists(srt_filename):
                    stub_name = f"{s_filename}.{conv_id}"
                    print(f"Encountered VobSub subtitle stream [{s_stream.title}] ({s_stream.idx})...")
                    idx_filename = f"{stub_name}.idx"
                    sub_filename = f"{stub_name}.sub"
                    if not os.path.exists(idx_filename) or not os.path.exists(sub_filename):
                        # Extract the VobSub subtitle
                        print(f"Extracting to {stub_name}")
                        # mkvextract tracks "$input_file" "$idx:$output_file"
                        out = subprocess.run([
                            "mkvextract", "tracks",
                            s_stream.filepath,
                            f"{s_stream.idx}:{stub_name}"], capture_output=True)
                        if out.returncode != 0:
                            raise ValueError(f"Failed to extract VobSub subtitle stream: {out.stderr.decode('utf-8')}")
                    # Convert to SRT
                    print(f"Converting to SRT")
                    # ./VobSub2SRT/bin/vobsub2srt subtitle
                    out = subprocess.run([
                        "./VobSub2SRT/bin/vobsub2srt", stub_name
                        ], capture_output=True)
                    if out.returncode != 0:
                        raise ValueError(f"Failed to convert VobSub subtitle to SRT: {out.stderr.decode('utf-8')}")
                    # Remove the original SUP file
                    os.remove(idx_filename)
                    os.remove(sub_filename)
                    if not os.path.exists(srt_filename):
                        raise ValueError(f"Failed to convert VobSub subtitle to SRT: {srt_filename} does not exist.")
                # Add the new SRT file to the session
                srt_cont = session.add_file(srt_filename)
                # Set the subtitle stream properties
                srt_cont.subtitle[0].language = s_stream.language
                srt_cont.subtitle[0].title = f"{s_stream.title} (OCR)"
                subtitle_map.append((srt_cont.subtitle[0], get_s_codec(srt_cont.subtitle[0])))
                conv_id += 1
        elif s_codec == "ass":
            mkv_needed = True
            subtitle_map.append((s_stream, s_codec))
            subtitle_map.append((s_stream, "subrip"))
        elif s_codec not in acceptable_subtitle_codecs:
            raise ValueError(f"Subtitle codec {s_codec} is not supported!")
        else:
            # We can copy the subtitle
            subtitle_map.append((s_stream, s_codec))

    # Pass 3: Convert streams to mov_text if possible
    def sub_pass_2(t: tuple[SubtitleStream,str]):
        s_stream = t[0]
        s_codec = get_s_codec(s_stream)
        target_codec = t[1]
        if s_codec == "hdmv_pgs_subtitle":
            pass
        elif s_codec == "dvd_subtitle":
            pass
        elif s_codec == "ass":
            pass
        else:
            # Otherwise try to convert to mov_text
            if not mkv_needed and s_codec != "mov_text":
                target_codec = "mov_text"
            else:
                pass
        return (s_stream, target_codec)

    subtitle_map = list(map(sub_pass_2, subtitle_map))

    # Pass 4: Sort subtitle streams by codec priority
    subtitle_streams_sorted = sorted(
        subtitle_map,
        key=lambda x: acceptable_subtitle_codecs.index(x[1]))

    s_idx = 0
    for s_stream, target_codec in subtitle_streams_sorted:
        f_stream_process(s_stream)
        file_idx = get_f_idx(s_stream)
        output_args += [ "-map", f"{file_idx}:{s_stream.idx}" ]
        sub_title = s_stream.title
        s_codec = get_s_codec(s_stream)

        if s_codec == target_codec:
            output_args += [ f"-c:s:{s_idx}", "copy" ]
        else:
            output_args += [ f"-c:s:{s_idx}", target_codec ]
            sub_title = f"{s_stream.title} ({target_codec})"

        if s_stream.language != "und":
            output_args += [ f"-metadata:s:s:{s_idx}", f"language={s_stream.language}" ]
        if sub_title != "":
            output_args += [ f"-metadata:s:s:{s_idx}", f"title={sub_title}" ]
        s_idx += 1

    # Set default streams
    output_args += [
        "-disposition:a:0", "default",
    ]
    if len(subtitle_streams_sorted) > 0:
        output_args += [
            "-disposition:s:0", "default",
        ]

    output_args += [ "-metadata", f"title={title}" ] if title else []

    if vid_cont.menu:
        output_args += [ "-map_chapters", "0"]

    output_args += [ "-map_metadata", "0"]

    # Build input argument list
    input_files = list(file_idx_map.keys())
    input_files = sorted(input_files, key=lambda x: file_idx_map[x])
    for input_file in input_files:
        # Add the input file to the input arguments
        input_args += [ "-i", f"file:{input_file}" ]

    # Add output file
    ffmpeg_cmd += input_args + output_args + [ f"file:{output_filepath}" ]

    # Print the command
    print("ffmpeg command:")
    print(" ".join(ffmpeg_cmd))

    if not cast(bool, args.dry_run):
        # Convert PGS subtitles

        # Run the command
        _ = subprocess.run(ffmpeg_cmd, capture_output=False, check=True)

        # Write metadata about input files
        metadata = {
            "input_files": inputs,
            "ffmpeg_cmd": " ".join(ffmpeg_cmd),
        }

        # replace the extension with .json
        metadata_filepath = os.path.splitext(output_filepath)[0]+".json"
        with open(metadata_filepath, "w") as f:
            _ = f.write(json.dumps(metadata, indent=4))


if __name__ == "__main__":
    main()
