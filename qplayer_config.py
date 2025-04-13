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
    VideoFraming = "VideoFraming"


class AlphaMode(StrEnum):
    Alpha = "Alpha"
    Mix = "Mix"
    GradientWipe = "GradientWipe"

    def to_number(self):
        if self == AlphaMode.Alpha:
            return 0
        elif self == AlphaMode.Mix:
            return 1
        elif self == AlphaMode.GradientWipe:
            return 2


class LoopMode(StrEnum):
    OneShot = "OneShot"
    Looped = "Looped"
    LoopedInfinite = "LoopedInfinite"


class StopMode(StrEnum):
    Immediate = "Immediate"
    LoopEnd = "LoopEnd"


class FadeType(StrEnum):
    Linear = "Linear"
    Exponential = "Exponential"
    Smooth = "Smooth"


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
        return default or list(enum_class)[0]


# === Point, and FramingShutter ===
@dataclass
class Point:
    x: float
    y: float


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
    startTime: Optional[timedelta] = None
    duration: Optional[timedelta] = None
    fadeIn: Optional[float] = None
    fadeOut: Optional[float] = None
    fadeType: Optional[FadeType] = None
    corners: Optional[List[Point]] = None
    framing: Optional[List[FramingShutter]] = None


@dataclass
class VideoCue(Cue):
    path: str
    shader: str = "default"
    zIndex: int = 0
    alphaPath: Optional[str] = None
    alphaMode: Optional[AlphaMode] = AlphaMode.Alpha
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


CueUnion = Union[
    GroupCue,
    DummyCue,
    SoundCue,
    TimeCodeCue,
    StopCue,
    VolumeCue,
    VideoCue,
    VideoFraming,
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


@dataclass
class QProjConfig:
    fileFormatVersion: int
    showMetadata: ShowMetadata
    columnWidths: List[float]
    cues: List[CueUnion]


def parse_point(p: List[float]) -> Point:
    if len(p) == 2:
        return Point(p[0], p[1])
    else:
        return Point(0, 0)


def parse_framing(f: Dict[str, Any]) -> FramingShutter:
    return FramingShutter(
        rotation=f.get("rotation", 0.0),
        maskStart=f.get("maskStart", 0.0),
        softness=f.get("softness", 0.0),
    )


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
            zIndex=data.get("zindex", 0),
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
            offset=parse_point(data["offset"]) if "offset" in data else Point(0, 0),
        )
    elif cue_type == CueType.VideoFraming:
        return VideoFraming(
            **base,
            startTime=parse_timecode(data.get("startTime", "00:00:00.00")),
            duration=parse_timecode(data.get("duration", "00:00:00.00")),
            fadeIn=data.get("fadeIn", 0.0),
            fadeOut=data.get("fadeOut", 0.0),
            fadeType=parse_enum(FadeType, data.get("fadeType")),
            corners=[
                parse_point(p)
                for p in data.get("corners", [[0, 0], [1, 0], [1, 1], [0, 1]])
            ],
            framing=[parse_framing(f) for f in data.get("framing", [{}, {}, {}, {}])],
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
    show_metadata = ShowMetadata(**data["showMetadata"])
    return QProjConfig(
        fileFormatVersion=data["fileFormatVersion"],
        showMetadata=show_metadata,
        columnWidths=data["columnWidths"],
        cues=cues,
    )
