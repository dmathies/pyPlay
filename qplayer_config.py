import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
from enum import StrEnum


# === Enums ===
class CueType(StrEnum):
    GroupCue = "GroupCue"
    DummyCue = "DummyCue"
    SoundCue = "SoundCue"
    TimeCodeCue = "TimeCodeCue"
    StopCue = "StopCue"
    VolumeCue = "VolumeCue"
    VideoCue = "VideoCue"
    VideoFramingCue = "VideoFramingCue"
    ShaderParamsCue = "ShaderParamsCue"


class AlphaMode(StrEnum):
    Opaque = "Opaque"  # Layer alpha comes from alpha uniform
    Video = "Video"  # Layer alpha comes from Video.a
    Alpha = "Alpha"  # Layer alpha comes from Video2.r
    GradientWipe = (
        "GradientWipe"  # Layer alpha comes from Video2.r applied as a gradient wipe
    )
    # Mix = "Mix"  # Alpha uniform blends between Video1.rgb and Video2.rgb

    def to_number(self):
        if self == AlphaMode.Opaque:
            return 0
        elif self == AlphaMode.Video:
            return 1
        elif self == AlphaMode.Alpha:
            return 2
        elif self == AlphaMode.GradientWipe:
            return 3


class LoopMode(StrEnum):
    OneShot = "OneShot"
    Looped = "Looped"
    LoopedInfinite = "LoopedInfinite"
    HoldLastFrame = "HoldLastFrame"


class StopMode(StrEnum):
    Immediate = "Immediate"
    LoopEnd = "LoopEnd"


class FadeType(StrEnum):
    Linear = "Linear"
    SCurve = "SCurve"
    Square = "Square"
    InverseSquare = "InverseSquare"


# === Timecode Utilities ===
def parse_timecode(time_str: str) -> timedelta:
    h, m, s = time_str.split(":")
    if "." in s:
        s, hh = s.split(".")
    else:
        hh = "0"

    return timedelta(
        hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(hh) * 10
    )


def format_timecode(td: timedelta) -> str:
    total_seconds = int(td.total_seconds())
    hundredths = (td.microseconds // 10000) % 100
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02}.{hundredths:02}"


def parse_enum(enum_class, value, default=None):
    try:
        return enum_class(value)
    except Exception:
        try:
            return default or list(enum_class)[value]
        except IndexError:
            return default

# === Point, and FramingShutter ===
@dataclass
class Point:
    x: float
    y: float


@dataclass
class ShaderParam:
    name: str
    value: float


@dataclass
class FramingShutter:
    rotation: float
    maskStart: float
    softness: float


@dataclass
class Cue:
    type: CueType
    qid: str
    parent: Optional[str]
    name: str
    description: str
    halt: bool
    enabled: bool
    delay: timedelta
    loopMode: LoopMode
    loopCount: int


@dataclass
class GroupCue(Cue):
    pass


@dataclass
class DummyCue(Cue):
    pass


@dataclass
class SoundCue(Cue):
    path: str
    startTime: timedelta
    duration: timedelta
    volume: float
    fadeIn: float
    fadeOut: float
    fadeType: FadeType


@dataclass
class TimeCodeCue(Cue):
    startTime: timedelta
    duration: timedelta


@dataclass
class StopCue(Cue):
    stopQid: str
    stopMode: StopMode
    fadeOutTime: float
    fadeType: FadeType


@dataclass
class VolumeCue(Cue):
    soundQid: str
    fadeTime: float
    volume: float
    fadeType: FadeType


@dataclass
class VideoFraming(Cue):
    fadeIn: float = 0
    fadeType: FadeType = FadeType.Linear
    corners: Optional[List[Point]] = None
    framing: Optional[List[FramingShutter]] = None


@dataclass
class VideoCue(Cue):
    path: str
    shader: str = "default"
    zIndex: int = 0
    alphaPath: Optional[str] = None
    stompsOthers: bool = False
    alphaMode: Optional[AlphaMode] = AlphaMode.Opaque
    alphaSoftness: Optional[float] = 0.0
    startTime: Optional[timedelta] = None
    duration: Optional[timedelta] = None
    dimmer: Optional[float] = None
    volume: Optional[float] = None
    fadeIn: Optional[float] = None
    fadeOut: Optional[float] = None
    fadeType: Optional[FadeType] = None
    brightness: Optional[float] = None
    contrast: Optional[float] = None
    gamma: Optional[float] = None
    scale: Optional[float] = 1.0
    rotation: Optional[float] = 0.0
    offset: Optional[Point] = None
    uniforms: Optional[list[ShaderParam]] = None


@dataclass
class ShaderParams(Cue):
    videoQid: str
    fadeIn: float = 0
    fadeType: FadeType = FadeType.Linear
    uniforms: Optional[list[ShaderParam]] = None


CueUnion = Union[
    GroupCue,
    DummyCue,
    SoundCue,
    TimeCodeCue,
    StopCue,
    VolumeCue,
    VideoCue,
    VideoFraming,
    ShaderParams,
]


VideoCueUnion = Union[
    VideoCue,
    VideoFraming,
    ShaderParams,
]


@dataclass
class ShowMetadata:
    title: str = "Untitled"
    description: str = ""
    author: str = ""
    date: str = datetime.today().isoformat()
    audioLatency: int = 100
    audioOutputDriver: int = 0
    audioOutputDevice: str = ""
    oscNIC: str = ""
    oscRXPort: int = 9000
    oscTXPort: int = 8000
    enableRemoteControl: bool = True
    isRemoteHost: bool = False
    syncShowFileOnSave: bool = False
    nodeName: str = "Video1"
    remoteNodes: tuple[dict[str, str]] = tuple()
    mscRXPort: int = 6004,
    mscTXPort: int = 6004,
    mscRXDevice: int = 112,
    mscTXDevice: int = 113,
    mscExecutor: int = -1,
    mscPage: int = -1

@dataclass
class QProjConfig:
    fileFormatVersion: int
    showSettings: ShowMetadata
    columnWidths: List[float]
    cues: List[CueUnion]


def parse_point(p: dict[str, float]) -> Point:
    return Point(p.get("X", 0), p.get("Y", 0))


def parse_framing(f: Dict[str, Any]) -> FramingShutter:
    return FramingShutter(
        rotation=f.get("rotation", 0.0),
        maskStart=f.get("maskStart", 0.0),
        softness=f.get("softness", 0.0),
    )


def parse_shader_param(p: dict[str, float]) -> ShaderParam:
    return ShaderParam(p.get("name", ""), p.get("value", 0))


def parse_cue(data: Dict[str, Any]) -> CueUnion:
    base = {
        "type": parse_enum(CueType, data["$type"]),
        "qid": str(data["qid"]),
        "parent": data.get("parent"),
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "halt": data.get("halt", True),
        "enabled": data.get("enabled", True),
        "delay": parse_timecode(data.get("delay", "00:00:00.00")),
        "loopMode": parse_enum(LoopMode, data.get("loopMode")),
        "loopCount": data.get("loopCount", 0),
    }

    cue_type = base["type"]
    if cue_type == CueType.SoundCue:
        return SoundCue(
            **base,
            path=data.get("path", ""),
            startTime=parse_timecode(data.get("startTime", "00:00:00.00")),
            duration=parse_timecode(data.get("duration", "00:00:00.00")),
            volume=data.get("volume", 1.0),
            fadeIn=data.get("fadeIn", 0.0),
            fadeOut=data.get("fadeOut", 0.0),
            fadeType=parse_enum(FadeType, data.get("fadeType")),
        )
    elif cue_type == CueType.TimeCodeCue:
        return TimeCodeCue(
            **base,
            startTime=parse_timecode(data.get("startTime", "00:00:00.00")),
            duration=parse_timecode(data.get("duration", "00:00:00.00")),
        )
    elif cue_type == CueType.StopCue:
        return StopCue(
            **base,
            stopQid=str(data.get("stopQid")),
            stopMode=parse_enum(StopMode, data.get("stopMode")),
            fadeOutTime=data.get("fadeOutTime", 0.0),
            fadeType=parse_enum(FadeType, data.get("fadeType")),
        )
    elif cue_type == CueType.VolumeCue:
        return VolumeCue(
            **base,
            soundQid=str(data.get("soundQid")),
            fadeTime=data.get("fadeTime", 0.0),
            volume=data.get("volume", 1.0),
            fadeType=parse_enum(FadeType, data.get("fadeType")),
        )
    elif cue_type == CueType.VideoCue:
        return VideoCue(
            **base,
            path=data.get("path", ""),
            zIndex=data.get("zIndex", 0),
            shader=data.get("shader", "default"),
            alphaPath=data.get("alphaPath", ""),
            alphaMode=parse_enum(AlphaMode, data.get("alphaMode")),
            alphaSoftness=data.get("alphaSoftness", 0.0),
            startTime=parse_timecode(data.get("startTime", "00:00:00.00")),
            duration=parse_timecode(data.get("duration", "00:00:00.00")),
            dimmer=data.get("dimmer", 1.0),
            volume=data.get("volume", 1.0),
            fadeIn=data.get("fadeIn", 0.0),
            fadeOut=data.get("fadeOut", 0.0),
            fadeType=parse_enum(FadeType, data.get("fadeType")),
            brightness=data.get("brightness", 1.0),
            contrast=data.get("contrast", 1.0),
            gamma=data.get("gamma", 1.0),
            scale=data.get("scale", 1.0),
            rotation=data.get("rotation", 0.0),
            stompsOthers=data.get("stompsOthers", False),
            offset=parse_point(data["offset"]) if "offset" in data else Point(0, 0),
            uniforms=[parse_shader_param(x) for x in data.get("uniforms", [])],
        )
    elif cue_type == CueType.VideoFramingCue:
        return VideoFraming(
            **base,
            fadeIn=data.get("fadeTime", 0.0),
            fadeType=parse_enum(FadeType, data.get("fadeType")),
            corners=[
                parse_point(p)
                for p in data.get("corners", [[0, 0], [1, 0], [0, 1], [1, 1]])
            ],
            framing=[parse_framing(f) for f in data.get("framing", [{}, {}, {}, {}])],
        )
    elif cue_type == CueType.ShaderParamsCue:
        return ShaderParams(
            **base,
            videoQid=str(data.get("targetQid")),
            fadeIn=data.get("fadeTime", 0.0),
            fadeType=parse_enum(FadeType, data.get("fadeType")),
            uniforms=[parse_shader_param(x) for x in data.get("uniforms", [])],
        )
    elif cue_type == CueType.GroupCue:
        return GroupCue(**base)
    elif cue_type == CueType.DummyCue:
        return DummyCue(**base)
    return DummyCue(**base)


def load_qproj(path: str) -> QProjConfig:
    with open(path, "r") as f:
        data = json.load(f)
    cues = [parse_cue(c) for c in data["cues"]]
    show_metadata = ShowMetadata(**data["showSettings"])
    return QProjConfig(
        fileFormatVersion=data["fileFormatVersion"],
        showSettings=show_metadata,
        columnWidths=data.get("columnWidths", []),
        cues=cues,
    )
