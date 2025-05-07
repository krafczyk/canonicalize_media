from typing import TypedDict

# Base for the always-present fields
class StreamInfoBase(TypedDict):
    index: int
    type: str
    codec: str

# Video streams get these extra fields
class VideoStreamInfo(StreamInfoBase, total=False):
    bit_rate: int
    profile: int
    profile_name: str
    level: int
    width: int
    height: int

# Audio streams only get bit_rate (beyond the base)
class AudioStreamInfo(StreamInfoBase, total=False):
    bit_rate: int

# A union covers either kind of stream
StreamInfo = VideoStreamInfo|AudioStreamInfo

# The top-level dict you return
class FFmpegInfo(TypedDict):
    streams: list[StreamInfo]

def ffmpeg(input_file: str) -> FFmpegInfo: ...
