from av_info import ffmpeg, mediainfo
from dataclasses import dataclass


@dataclass
class VideoStream:
    filepath: str
    idx: int
    codec: str
    profile: str
    level: int
    bit_rate: float
    bit_depth: int
    color_encoding: str


@dataclass
class AudioStream:
    filepath: str
    idx: int
    codec: str
    channels: int
    bit_rate: float
    language: str
    title: str


@dataclass
class TextStream:
    filepath: str
    idx: int
    codec: str
    language: str
    title: str


class MediaContainer:
    def __init__(self, filepath):
        self.filepath = filepath
        self.ffmpeg = ffmpeg(filepath)
        self.mediainfo = mediainfo(filepath)
