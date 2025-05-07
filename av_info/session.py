from av_info.mediainfo import mediainfo, MediaInfo
from av_info._ffmpeg import ffmpeg, FFmpegInfo, VideoStreamInfo, AudioStreamInfo
from dataclasses import dataclass
from pprint import pprint
from typing import override


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
    title: str

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


def get_ffmpeg_streams(ffmpeg_data: FFmpegInfo):
    streams = {'video': [], 'audio': [], 'subtitle': []}
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


def get_mediainfo_streams(mediainfo_data):
    streams = {'video': [], 'audio': [], 'subtitle': []}
    tracks = mediainfo_data['media']['track']
    for track in tracks[1:]:
        if track['@type'] == 'Video':
            streams['video'].append(track)
        elif track['@type'] == 'Audio':
            streams['audio'].append(track)
        elif track['@type'] == 'Text':
            streams['subtitle'].append(track)
    gen_track = tracks[0]
    assert len(streams['video']) == int(gen_track.get('VideoCount', 0))
    assert len(streams['audio']) == int(gen_track.get('AudioCount', 0))
    assert len(streams['subtitle']) == int(gen_track.get('TextCount', 0))
    return streams


class MediaContainer:
    filepath: str
    mediainfo: MediaInfo
    ffmpeg: FFmpegInfo
    video: list[VideoStreamInfo]
    audio: list[AudioStreamInfo]

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.ffmpeg = ffmpeg(filepath)
        self.mediainfo = mediainfo(filepath)

        self.video = []
        self.audio = []
        #self.subtitle = []


    def analyze(self):
        ffmpeg_streams = get_ffmpeg_streams(self.ffmpeg)
        mediainfo_streams = get_mediainfo_streams(self.mediainfo)
        assert len(ffmpeg_streams['video']) == len(mediainfo_streams['video'])
        assert len(ffmpeg_streams['audio']) == len(mediainfo_streams['audio'])
        assert len(ffmpeg_streams['subtitle']) == len(mediainfo_streams['subtitle'])

        n_videos = len(ffmpeg_streams['video'])
        n_audio = len(ffmpeg_streams['audio'])
        n_subtitle = len(ffmpeg_streams['subtitle'])

        for i in range(len(ffmpeg_streams['video'])):
            idx = int(ffmpeg_streams['video'][i]['index'])
            assert idx == (int(mediainfo['video'][i]['ID'])-1)
            codec = mediainfo['video'][i]['Format']
            level = mediainfo['video'][i]['Format_Level']
            profile = mediainfo['video'][i]['Format_Profile']
            bit_rate = float(mediainfo['video'][i]['BitRate'])/1024.
            bit_depth = int(mediainfo['video'][i]['BitDepth'])
            frame_rate = float(mediainfo['video'][i]['FrameRate'])
            width = int(mediainfo['video'][i]['Width'])
            height = int(mediainfo['video'][i]['Height'])
            aspect_ratio = float(mediainfo['video'][i]['DisplayAspectRatio'])
            color_space = mediainfo['video'][i]['ColorSpace']
            chroma_subsampling = mediainfo['video'][i]['ChromaSubsampling']
            if 'HDR_Format' in mediainfo['video'][i]:
                hdr = (
                    mediainfo['video'][i]['HDR_Format'],
                    mediainfo['video'][i]['HDR_Compatibility'],
                    mediainfo['video'][i]['color_primaries'])
            else:
                hdr = None

            v_stream = VideoStream(
                self.filepath,
                idx,
                codec,
                level,
                profile,
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
            idx = int(ffmpeg_streams['audio'][i]['index'])
            assert idx == (int(mediainfo['audio'][i]['ID'])-1)
            codec = mediainfo['audio'][i]['Format']
            channels = int(mediainfo['audio'][i]['Channel(s)'])

        pprint(ffmpeg_streams)
        pprint(mediainfo_streams)
