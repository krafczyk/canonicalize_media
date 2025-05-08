from av_info.mediainfo import mediainfo, MediaInfo, Video, Audio, Text, Menu, General
from av_info._ffmpeg import ffmpeg, FFmpegInfo, VideoStreamInfo, AudioStreamInfo, SubtitleStreamInfo
from dataclasses import dataclass
from pprint import pprint
from typing import override, TypedDict


@dataclass
class VideoStream:
    filepath: str
    idx: int
    codec: str
    profile: str
    level: int
    bit_rate: float # rate kb/s
    bit_depth: int
    frame_rate: float
    width: int
    height: int
    aspect_ratio: float
    color_space: str
    chroma_subsampling: str
    hdr_format: tuple[str, str, str] | None

    @override
    def __str__(self):
        return f"{self.filepath},{self.idx}: {self.codec}@L{self.level}@{self.profile} {self.bit_rate} {self.bit_depth} {self.frame_rate} {self.width}x{self.height} {self.aspect_ratio} {self.color_space} {self.chroma_subsampling} HDR: {self.hdr_format}"


@dataclass
class AudioStream:
    filepath: str
    idx: int
    codec: str
    channels: int
    bit_rate: float
    language: str
    title: str | None

    @override
    def __str__(self):
        return f"{self.filepath},{self.idx}: {self.codec} {self.channels} {self.bit_rate} {self.language} {self.title}"


@dataclass
class TextStream:
    filepath: str
    idx: int
    codec: str
    language: str
    title: str

    @override
    def __str__(self):
        return f"{self.filepath},{self.idx}: {self.codec} {self.language} {self.title}"


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
            raise RuntimeError(f"Unexpected stream type: {stream['type']}")
    return streams


class MediaInfoStreams(TypedDict):
    video: list[Video]
    audio: list[Audio]
    subtitle: list[Text]
    menu: list[Menu]


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
        elif isinstance(track, Menu):
            streams['menu'].append(track)
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

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.ffmpeg = ffmpeg(filepath)
        self.mediainfo = mediainfo(filepath)

        self.video = []
        self.audio = []
        #self.subtitle = []


    def analyze(self):
        ffmpeg_streams: FFmpegStreams = get_ffmpeg_streams(self.ffmpeg)
        mediainfo_streams: MediaInfoStreams = get_mediainfo_streams(self.mediainfo)
        assert len(ffmpeg_streams['video']) == len(mediainfo_streams['video'])
        assert len(ffmpeg_streams['audio']) == len(mediainfo_streams['audio'])
        assert len(ffmpeg_streams['subtitle']) == len(mediainfo_streams['subtitle'])

        for i in range(len(ffmpeg_streams['video'])):
            fs = ffmpeg_streams['video'][i]
            ms = mediainfo_streams['video'][i]
            idx = int(fs['index'])
            assert idx == (ms.ID-1)
            codec = ms.Format
            level = ms.Format_Level
            profile = ms.Format_Profile
            bit_rate = float(ms.BitRate)/1024.
            bit_depth = ms.BitDepth
            frame_rate = float(ms.FrameRate)
            width = ms.Width
            height = ms.Height
            aspect_ratio = ms.DisplayAspectRatio
            color_space = ms.ColorSpace
            chroma_subsampling = ms.ChromaSubsampling
            hdr: tuple[str, str, str] | None = None
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

            a_stream = AudioStream(
                self.filepath,
                idx,
                codec,
                channels,
                float(ms.BitRate)/1024.,
                ms.Language,
                fs['title']
            )

            self.audio.append(a_stream)

        pprint(ffmpeg_streams)
        pprint(mediainfo_streams)

        pprint(self.video)
        pprint(self.audio)
