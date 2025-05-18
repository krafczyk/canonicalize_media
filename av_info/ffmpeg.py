from typing import TypedDict, Literal, Required

# Base for the always-present fields
class StreamInfoBase(TypedDict):
    index: int
    codec: str

# Video streams get these extra fields
class VideoStreamInfo(StreamInfoBase, total=False):
    type: Required[Literal["video"]]
    bit_rate: int
    profile: int
    profile_name: str
    level: int
    width: int
    height: int

# Audio streams only get bit_rate (beyond the base)
class AudioStreamInfo(StreamInfoBase, total=False):
    type: Required[Literal["audio"]]
    bit_rate: int
    title: Required[str | None]

class SubtitleStreamInfo(StreamInfoBase, total=False):
    type: Required[Literal["subtitle"]]
    language: Required[str]
    title: str
    codec: Required[str]
    codec_long: Required[str]
    format: Required[str]

# A union covers either kind of stream
StreamInfo = VideoStreamInfo|AudioStreamInfo|SubtitleStreamInfo

# The top-level dict you return
class FFmpegInfo(TypedDict):
    streams: list[StreamInfo]

from av_info._ffmpeg import ffmpeg

__all__ = ["ffmpeg"]
