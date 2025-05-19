import argparse
from av_info import MediaContainer
from av_info.session import VideoStream, AudioStream, SubtitleStream
from typing import cast
import subprocess


acceptable_subtitle_codecs = ['subrip']


if __name__ == "__main__":
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser()
    # An input argument that takes a list of filepaths

    _ = parser.add_argument("--output", "-o", help="The output file to write to.", required=True)
    _ = parser.add_argument("--input", "-i", nargs="+", help="Input file(s), format is <filename>@@<Title>@@<Language> where the two extra fields are only relevant for extra audio/subtitle tracks.", required=True)
    _ = parser.add_argument("--dry-run", help="Only construct the command, do not run it.", action="store_true")
    args = parser.parse_args()

    inputs: list[str] = cast(list[str], args.input)

    containers: list[MediaContainer] = []

    # collate all streams
    video_streams: list[VideoStream] = []
    audio_streams: list[AudioStream] = []
    subtitle_streams: list[SubtitleStream] = []

    filename_cont_map: dict[str, MediaContainer] = {}
    idx = 0
    for i in inputs:
        input_file = i
        if '@@' in i:
            input_file = i.split('@@')[0]

        file_cont = MediaContainer(idx, input_file)
        file_cont.analyze()
        stream_lengths = (len(file_cont.video), len(file_cont.audio), len(file_cont.subtitle))
        if len(file_cont.subtitle) == 1 and sum(stream_lengths) == 1:
            title = i.split('@@')[1]
            language = i.split('@@')[2]
            file_cont.subtitle[0].title = title
            file_cont.subtitle[0].language = language
        if len(file_cont.audio) == 1 and sum(stream_lengths) == 1:
            title = i.split('@@')[1]
            language = i.split('@@')[2]
            file_cont.audio[0].title = title
            file_cont.audio[0].language = language
        containers.append(file_cont)
        filename_cont_map[file_cont.filepath] = file_cont

        video_streams += file_cont.video
        audio_streams += file_cont.audio
        subtitle_streams += file_cont.subtitle
        idx += 1

    if len(video_streams) == 0:
        raise ValueError("No video streams found.")
    if len(video_streams) > 1:
        raise ValueError("Only one video stream is supported!")


    # Build ffmpeg command
    ffmpeg_cmd = [ "ffmpeg" ]
    # Add input files
    for cont in containers:
        ffmpeg_cmd += ["-i", cont.filepath ]

    # Selected video stream
    vid_cont = filename_cont_map[video_streams[0].filepath]
    stream_id = vid_cont.idx
    ffmpeg_cmd += [ "-map", f"{stream_id}:0" ]

    if vid_cont.menu:
        ffmpeg_cmd += [ "-map_chapters", "0"]

    ffmpeg_cmd += [ "-map_metadata", "0"]

    # Specify video encoder
    ffmpeg_cmd += [ "-c:v", "copy" ]

    # Sort audio streams english streams first, 5.1 first
    audio_streams_sorted = sorted(audio_streams, key=lambda x: (x.language != "eng", x.channels != 6))

    for a_stream in audio_streams_sorted:
        stream_id = filename_cont_map[a_stream.filepath].idx
        ffmpeg_cmd += [ "-map", f"{stream_id}:{a_stream.idx}" ]

    # Specify audio encoder
    ffmpeg_cmd += [ "-c:a", "copy" ]

    # Sort subtitle streams english streams first
    subtitle_streams_sorted = sorted(subtitle_streams, key=lambda x: (x.language != "eng"))

    s_idx = 0
    for s_stream in subtitle_streams_sorted:
        if s_stream.codec not in acceptable_subtitle_codecs:
            raise ValueError(f"Subtitle codec {s_stream.codec} is not supported!")
        stream_id = filename_cont_map[s_stream.filepath].idx
        ffmpeg_cmd += [ "-map", f"{stream_id}:0" ]
        if s_stream.language != "und":
            ffmpeg_cmd += [ f"-metadata:s:s:{s_idx}", f"language={s_stream.language}" ]
        if s_stream.title != "":
            ffmpeg_cmd += [ f"-metadata:s:s:{s_idx}", f"title={s_stream.title}" ]
        s_idx += 1

    # Set subtitle codec
    ffmpeg_cmd += [ "-c:s", "mov_text" ] # by default translate to mov_text

    # Add output file
    ffmpeg_cmd += [cast(str,args.output)]

    # Print the command
    print("ffmpeg command:")
    print(" ".join(ffmpeg_cmd))

    # Run the command
    if not cast(bool, args.dry_run):
        _ = subprocess.run(ffmpeg_cmd, capture_output=False, check=True)
