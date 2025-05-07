import subprocess
from pydantic import BaseModel, Field
from typing import Annotated, Literal


class MILibrary(BaseModel):
    name: str
    version: str
    url: str


class General(BaseModel):
    kind: Literal["General"] = Field(..., alias="@type")
    UniqueID: str
    VideoCount: int
    AudioCount: int
    TextCount: int
    MenuCount: int
    FileExtension: str
    Format: str
    Format_Version: int
    FileSize: int
    Duration: float
    OverallBitRate: int
    FrameRate: float
    FrameCount: int
    StreamSize: int
    IsStreamable: str
    Title: str
    Movie: str
    Encoded_Date: str
    File_Modified_Date: str
    File_Modified_Date_Local: str
    Encoded_Application: str
    Encoded_Library: str


class Video(BaseModel):
    kind: Literal["Video"] = Field(..., alias="@type")
    StreamOrder: int
    ID: int
    UniqueID: str
    Format: str
    Format_Profile: str
    Format_Level: int
    Format_Tier: str
    HDR_Format: str
    HDR_Format_Version: str
    HDR_Format_Profile: str
    HDR_Format_Level: str
    HDR_Format_Settings: str
    HDR_Format_Compression: str
    HDR_Format_Compatibility: str
    CodecID: str
    Duration: float
    BitRate: int
    Width: int
    Height: int
    Stored_Height: int
    Sampled_Width: int
    Sampled_Height: int
    PixelAspectRatio: float
    DisplayAspectRatio: float
    FrameRate_Mode: str
    FrameRate: float
    FrameRate_Num: int
    FrameRate_Den: int
    FrameCount: int
    ColorSpace: str
    ChromaSubsampling: str
    ChromaSubsampling_Position: str
    BitDepth: int
    Delay: float
    Delay_Source: str
    StreamSize: int
    Default: str
    Forced: str
    colour_description_present: str
    colour_range_Source: str
    colour_primaries: str
    colour_primaries_Source: str
    transfer_characteristics: str
    transfer_characteristics_Source: str
    matrix_coefficients: str
    matrix_coefficients_Source: str
    MasteringDisplay_ColorPrimaries: str
    MasteringDisplay_ColorPrimaries_Source: str
    MasteringDisplay_Luminance: str
    MasteringDisplay_Luminance_Source: str
    MaxCLL: str
    MaxCLL_Source: str
    MaxFALL: str
    MaxFALL_Source: str


class Audio(BaseModel):
    kind: Literal["Audio"] = Field(..., alias="@type")
    StreamOrder: int
    ID: int
    UniqueID: str
    Format: str
    Format_Commercial_IfAny: str
    Format_Settings_SBR: str
    Format_AdditionalFeatures: str
    CodecID: str
    Duration: float
    BitRate: int
    Channels: int
    ChannelPositions: str
    ChannelLayout: str
    SamplesPerFrame: int
    SamplingRate: int
    SamplingCount: int
    FrameRate: float
    FrameCount: int
    Compression_Mode: str
    Delay: float
    Delay_Source: str
    Video_Delay: float
    StreamSize: int
    Language: str
    Default: str
    Forced: str


class Text(BaseModel):
    kind: Literal["Text"] = Field(..., alias="@type")
    typeorder: int = Field(..., alias="@typeorder")
    StreamOrder: int
    ID: int
    UniqueID: str
    Format: str
    CodecID: str
    Duration: float
    BitRate: int
    FrameRate: float
    FrameCount: int
    ElementCount: int
    StreamSize: int
    Language: str
    Default: str
    Forced: str


class Menu(BaseModel):
    kind: Literal["Menu"] = Field(..., alias="@type")
    extra: dict[str,str]


Track = Annotated[
    General|Video|Audio|Text|Menu,
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
