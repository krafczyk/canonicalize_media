from av_info.mediainfo import mediainfo, MediaInfo, Video, Audio, Text, General
from av_info.mediainfo import Menu as MIMenu
from av_info.ffmpeg import ffmpeg, FFmpegInfo, VideoStreamInfo, AudioStreamInfo, SubtitleStreamInfo
from av_info.utils import guess_lang_from_filename
from dataclasses import dataclass
from pprint import pprint
from typing import override, TypedDict
import os


@dataclass
class VideoStream:
    filepath: str
    idx: int
    codec: str
    profile: str
    level: str
    bit_rate: float # rate kb/s
    bit_depth: int
    frame_rate: float | None
    width: int
    height: int
    aspect_ratio: float
    color_space: str
    chroma_subsampling: str
    hdr_format: tuple[str, str, str|None] | None

    @override
    def __str__(self):
        return f"{self.filepath},{self.idx}: {self.codec}@L{self.level}@{self.profile} {self.bit_rate} {self.bit_depth} {self.frame_rate} {self.width}x{self.height} {self.aspect_ratio} {self.color_space} {self.chroma_subsampling} HDR: {self.hdr_format}"


@dataclass
class AudioStream:
    filepath: str
    idx: int
    codec: str
    channels: int
    bit_rate: float | None
    language: str | None
    title: str | None

    @override
    def __str__(self):
        return f"{self.filepath},{self.idx}: {self.codec} {self.channels} {self.bit_rate} {self.language} {self.title}"


@dataclass
class SubtitleStream:
    filepath: str
    idx: int
    format: str
    codec: str
    codec_long: str
    language: str
    title: str | None

    @override
    def __str__(self):
        return f"{self.filepath},{self.idx}: {self.format} {self.language} {self.title}"


@dataclass
class Menu:
    filepath: str

    @override
    def __str__(self):
        return f"{self.filepath}"


class FFmpegStreams(TypedDict):
    video: list[VideoStreamInfo]
    audio: list[AudioStreamInfo]
    subtitle: list[SubtitleStreamInfo]


def get_ffmpeg_streams(ffmpeg_data: FFmpegInfo) -> FFmpegStreams:
    streams: FFmpegStreams = {'video': [], 'audio': [], 'subtitle': []}
    for stream in ffmpeg_data['streams']:
        if stream['type'] == 'video':
            streams['video'].append(stream)
        elif stream['type'] == 'audio':
            streams['audio'].append(stream)
        elif stream['type'] == 'subtitle':
            streams['subtitle'].append(stream)
        else:
            print(f"WARNING: Skipping stream with unexpected type: {stream['type']}")
    return streams


class MediaInfoStreams(TypedDict):
    video: list[Video]
    audio: list[Audio]
    subtitle: list[Text]
    menu: list[MIMenu]


def get_mediainfo_streams(mediainfo_data: MediaInfo) -> MediaInfoStreams:
    streams: MediaInfoStreams = {'video': [], 'audio': [], 'subtitle': [], 'menu': []}
    tracks = mediainfo_data.media.track
    for track in tracks[1:]:
        if isinstance(track, Video):
            streams['video'].append(track)
        elif isinstance(track, Audio):
            streams['audio'].append(track)
        elif isinstance(track, Text):
            streams['subtitle'].append(track)
        elif isinstance(track, MIMenu):
            streams['menu'].append(track)
        else:
            raise RuntimeError(f"Unexpected track type: {type(track)}")
    if not isinstance(tracks[0], General):
        raise TypeError("Expected a General track first.")
    gen_track = tracks[0]
    assert len(streams['video']) == int(gen_track.VideoCount)
    assert len(streams['audio']) == int(gen_track.AudioCount)
    assert len(streams['subtitle']) == int(gen_track.TextCount)
    assert len(streams['menu']) == int(gen_track.MenuCount)
    return streams


class MediaContainer:
    filepath: str
    mediainfo: MediaInfo
    ffmpeg: FFmpegInfo
    video: list[VideoStream]
    audio: list[AudioStream]
    subtitle: list[SubtitleStream]
    menu: bool

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.ffmpeg = ffmpeg(filepath)
        self.mediainfo = mediainfo(filepath)

        self.video = []
        self.audio = []
        self.subtitle = []
        self.menu = False


    def analyze(self):
        ffmpeg_streams: FFmpegStreams = get_ffmpeg_streams(self.ffmpeg)
        mediainfo_streams: MediaInfoStreams = get_mediainfo_streams(self.mediainfo)
        assert len(ffmpeg_streams['video']) == len(mediainfo_streams['video'])
        assert len(ffmpeg_streams['audio']) == len(mediainfo_streams['audio'])

        for i in range(len(ffmpeg_streams['video'])):
            fs = ffmpeg_streams['video'][i]
            ms = mediainfo_streams['video'][i]
            idx = int(fs['index'])
            assert idx == (ms.ID-1)
            codec = ms.Format
            level = ms.Format_Level
            profile = ms.Format_Profile
            bit_rate: float
            if ms.BitRate is None:
                if "bit_rate" not in fs:
                    raise ValueError("Unable to guess bitrate of video!")
                bit_rate = fs["bit_rate"]/1024.
            else:
                bit_rate = float(ms.BitRate)/1024.
            bit_depth = ms.BitDepth
            frame_rate: float|None = None
            if ms.FrameRate is not None:
                frame_rate = float(ms.FrameRate)
            width = ms.Width
            height = ms.Height
            aspect_ratio = ms.DisplayAspectRatio
            color_space = ms.ColorSpace
            chroma_subsampling = ms.ChromaSubsampling
            hdr: tuple[str, str, str|None] | None = None
            if ms.HDR_Format is not None and ms.HDR_Format_Compatibility is not None:
                hdr = (
                    ms.HDR_Format,
                    ms.HDR_Format_Compatibility,
                    ms.colour_primaries)

            v_stream = VideoStream(
                self.filepath,
                idx,
                codec,
                profile,
                level,
                bit_rate,
                bit_depth,
                frame_rate,
                width,
                height,
                aspect_ratio,
                color_space,
                chroma_subsampling,
                hdr
            )

            self.video.append(v_stream)

        for i in range(len(ffmpeg_streams['audio'])):
            fs = ffmpeg_streams['audio'][i]
            ms = mediainfo_streams['audio'][i]
            idx = int(fs['index'])
            assert idx == ms.ID-1
            codec = ms.Format
            channels = ms.Channels
            bit_rate: float | None
            if ms.BitRate is None:
                if "bit_rate" in fs:
                    bit_rate = fs["bit_rate"]/1024.
                else:
                    bit_rate = None
            else:
                bit_rate = ms.BitRate/1024.

            a_stream = AudioStream(
                self.filepath,
                idx,
                codec,
                channels,
                bit_rate,
                ms.Language if ms.Language else fs.get('language', "und"),
                fs.get('title', None)
            )

            self.audio.append(a_stream)

        if len(mediainfo_streams['menu']) > 0:
            self.menu = True

        for i in range(len(ffmpeg_streams['subtitle'])):
            fs = ffmpeg_streams['subtitle'][i]
            #ms = mediainfo_streams['subtitle'][i]
            idx = int(fs['index'])
            format = fs['format']
            language = fs['language']
            codec = fs['codec']
            codec_long = fs['codec_long']
            title = fs.get("title", None)

            t_stream = SubtitleStream(
                self.filepath,
                idx,
                format,
                codec,
                codec_long,
                language,
                title
            )

            self.subtitle.append(t_stream)


    def summarize(self):
        print(f"filepath: {self.filepath}")
        print(f"video streams:")
        print(self.video)
        print(f"audio streams:")
        print(self.audio)
        print(f"subtitle streams:")
        print(self.subtitle)
        if self.menu:
            print("Contains a menu")
        else:
            print("Doesn't contain a menu")


class Session:
    video_streams: list[VideoStream]
    audio_streams: list[AudioStream]
    subtitle_streams: list[SubtitleStream]
    filename_cont_map: dict[str, MediaContainer]

    def __init__(self, inputs: list[str] | None = None):
        # collate all streams
        self.video_streams = []
        self.audio_streams = []
        self.subtitle_streams = []

        self.filename_cont_map = {}

        if inputs is not None:
            self.add_files(inputs)

    def add_files(self, files: list[str]):
        for f in files:
            _ = self.add_file(f)

    def add_file(self, filespec: str) -> MediaContainer:
        input_file = filespec
        if '@@' in filespec:
            input_file = filespec.split('@@')[0]

        file_cont = MediaContainer(input_file)
        file_cont.analyze()

        stream_lengths = (len(file_cont.video), len(file_cont.audio), len(file_cont.subtitle))
        if len(file_cont.subtitle) == 1 and sum(stream_lengths) == 1:
            # This is a single subtitle stream
            sub_title: str
            language: str
            if '@@' in filespec:
                title_components = filespec.split('@@')
                if len(title_components) == 2:
                    sub_title = title_components[1]
                    l = guess_lang_from_filename(sub_title)
                    if l is None:
                        raise ValueError(f"Could not guess language from title {sub_title}")
                    language = l
                elif len(title_components) == 3:
                    sub_title = title_components[1]
                    language = title_components[2]
                else:
                    raise ValueError(f"Invalid input format: {filespec}. Expected <filename>@@<Title>@@<Language>")
            else:
                # Guess language from filename, use filename without extension as title
                sub_title = os.path.splitext(os.path.basename(filespec))[0]
                l = guess_lang_from_filename(filespec)
                if l is None:
                    raise ValueError(f"Could not guess language from filename {filespec}")
                language = l
            file_cont.subtitle[0].title = sub_title
            file_cont.subtitle[0].language = language
        if len(file_cont.audio) == 1 and sum(stream_lengths) == 1:
            sub_title = filespec.split('@@')[1]
            language = filespec.split('@@')[2]
            file_cont.audio[0].title = sub_title
            file_cont.audio[0].language = language
        self.filename_cont_map[file_cont.filepath] = file_cont

        self.video_streams += file_cont.video
        self.audio_streams += file_cont.audio
        self.subtitle_streams += file_cont.subtitle

        return file_cont
