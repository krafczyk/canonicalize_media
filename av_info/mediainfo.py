import subprocess
from pydantic import BaseModel, Field
from typing import Annotated, Literal


class MILibrary(BaseModel):
    name: str
    version: str
    url: str


class General(BaseModel):
    kind: Literal["General"] = Field(alias='@type')
    UniqueID: str | None = None
    VideoCount: int = 0
    AudioCount: int = 0
    TextCount: int = 0
    MenuCount: int = 0
    FileExtension: str
    Format: str | None = None
    Format_Version: int | None = None
    FileSize: int
    Duration: float | None = None
    OverallBitRate: int | None = None
    FrameRate: float | None = None
    FrameCount: int | None = None
    StreamSize: int | None = None
    IsStreamable: str | None = None
    Title: str | None = None
    Movie: str | None = None
    Encoded_Date: str | None = None
    File_Modified_Date: str
    File_Modified_Date_Local: str
    Encoded_Application: str | None = None
    Encoded_Library: str | None = None


class Video(BaseModel):
    kind: Literal["Video"] = Field(alias='@type')
    StreamOrder: int | None = None
    ID: int
    UniqueID: str | None = None
    Format: str
    Format_Profile: str | None = None
    Format_Level: str | None = None
    Format_Tier: str | None = None
    HDR_Format: str | None = None
    HDR_Format_Version: str | None = None
    HDR_Format_Profile: str | None = None
    HDR_Format_Level: str | None = None
    HDR_Format_Settings: str | None = None
    HDR_Format_Compression: str | None = None
    HDR_Format_Compatibility: str | None = None
    CodecID: str
    Duration: float
    BitRate: int | None = None
    Width: int
    Height: int
    Stored_Height: int | None = None
    Sampled_Width: int | None = None
    Sampled_Height: int | None = None
    PixelAspectRatio: float
    DisplayAspectRatio: float
    FrameRate_Mode: str | None = None
    FrameRate: float | None = None
    FrameRate_Num: int | None = None
    FrameRate_Den: int | None = None
    FrameCount: int | None = None
    ColorSpace: str | None = None
    ChromaSubsampling: str | None = None
    ChromaSubsampling_Position: str | None = None
    BitDepth: int | None = None
    Delay: float | None = None
    Delay_Source: str | None = None
    StreamSize: int | None = None
    Default: str | None = None
    Forced: str | None = None
    colour_description_present: str | None = None
    colour_range_Source: str | None = None
    colour_primaries: str | None = None
    colour_primaries_Source: str | None = None
    transfer_characteristics: str | None = None
    transfer_characteristics_Source: str | None = None
    matrix_coefficients: str | None = None
    matrix_coefficients_Source: str | None = None
    MasteringDisplay_ColorPrimaries: str | None = None
    MasteringDisplay_ColorPrimaries_Source: str | None = None
    MasteringDisplay_Luminance: str | None = None
    MasteringDisplay_Luminance_Source: str | None = None
    MaxCLL: str | None = None
    MaxCLL_Source: str | None = None
    MaxFALL: str | None = None
    MaxFALL_Source: str | None = None


class Audio(BaseModel):
    kind: Literal["Audio"] = Field(alias='@type')
    StreamOrder: int
    ID: int
    UniqueID: str | None = None
    Format: str
    Format_Commercial_IfAny: str | None = None
    Format_Settings_SBR: str | None = None
    Format_AdditionalFeatures: str | None = None
    CodecID: str
    Duration: float
    BitRate: int | None = None
    Channels: int
    ChannelPositions: str | None = None
    ChannelLayout: str | None = None
    SamplesPerFrame: int | None = None
    SamplingRate: int
    SamplingCount: int
    FrameRate: float | None = None
    FrameCount: int | None = None
    Compression_Mode: str
    Delay: float | None = None
    Delay_Source: str | None = None
    Video_Delay: float | None = None
    StreamSize: int | None = None
    Language: str | None = None
    Default: str | None = None
    Forced: str | None = None


class Text(BaseModel):
    kind: Literal["Text"] = Field(alias='@type')
    typeorder: int | None = Field(None, alias="@typeorder")
    StreamOrder: int | None = None
    ID: int | None = None
    UniqueID: str | None = None
    Format: str
    CodecID: str | None = None
    Duration: float | None = None
    Duration_Start: float | None = None
    Duration_End: float | None = None
    Compression_Mode: str | None = None
    Events_Total: int | None = None
    Events_MinDuration: float | None = None
    Lines_Count: int | None = None
    Lines_MaxCountPerEvent: int | None = None
    BitRate: int | None = None
    FrameRate: float | None = None
    FrameCount: int | None = None
    ElementCount: int | None = None
    StreamSize: int | None = None
    Language: str | None = None
    Default: str | None = None
    Forced: str | None = None


class Image(BaseModel):
    kind: Literal["Image"] = Field(alias='@type')
    typeorder: int | None = Field(None, alias="@typeorder")
    StreamOrder: int | None = None
    ID: int | None = None
    UniqueID: str | None = None
    Format: str
    CodecID: str | None = None
    Duration: float | None = None
    Duration_Start: float | None = None
    Duration_End: float | None = None
    Compression_Mode: str | None = None
    Events_Total: int | None = None
    Events_MinDuration: float | None = None
    Lines_Count: int | None = None
    Lines_MaxCountPerEvent: int | None = None
    BitRate: int | None = None
    FrameRate: float | None = None
    FrameCount: int | None = None
    ElementCount: int | None = None
    StreamSize: int | None = None
    Language: str | None = None
    Default: str | None = None
    Forced: str | None = None


class Menu(BaseModel):
    kind: Literal["Menu"] = Field(alias='@type')
    extra: dict[str,str] | None = None


Track = Annotated[
    General|Video|Audio|Text|Menu|Image,
    Field(discriminator='kind')
]


class Media(BaseModel):
    ref: str = Field(..., alias="@ref")
    track: list[Track]


class MediaInfo(BaseModel):
    creatingLibrary: MILibrary
    media: Media


def mediainfo(filepath:str) -> MediaInfo:
    # Get output from the mediainfo command-line tool
    output = subprocess.check_output(["mediainfo", "--Output=JSON", filepath])
    return MediaInfo.model_validate_json(output)
