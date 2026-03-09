from enum import IntEnum
from enum import IntEnum
from typing import Iterator, Optional
import av
from av.container import InputContainer, OutputContainer
import threading
import numpy as np
import pygame

try:
    import OpenEXR  # type: ignore
    import Imath  # type: ignore
except ImportError:
    OpenEXR = None
    Imath = None


class VideoFrameFormat(IntEnum):
    RGB = 0
    NV12 = 1
    YUVJ420p = 2
    GRAY = 3


class VideoFrameColourSpace(IntEnum):
    RGB = 0
    BT601 = 1
    BT709 = 2


class VideoStatus(IntEnum):
    LOADING = 0
    LOADED = 1
    READY = 2
    EMPTY = -1


class VideoData:
    def __init__(self):
        self.container: Optional[InputContainer | OutputContainer] = None
        self.video_stream: av.VideoStream | None = None
        self.gen: Optional[Iterator[av.VideoFrame]] = None
        self.frame_format: Optional[int] = None
        self.width = 0
        self.height = 0
        self.textures = {}
        self.frame_pix_format = None
        self.colour_space = VideoFrameColourSpace.RGB
        self.still = False
        self.status = VideoStatus.EMPTY
        self.current_frame = None
        self.seek_start_seconds = 0.0
        self.hdr_still = False
        self.rgba_still = False

    def release(self):
        # Close AV container / decoder
        if self.container is not None:
            try:
                # This tears down the codec + hwaccel context
                self.container.close()
            except Exception as e:
                print(f"[VideoData] Error closing container: {e}")

        self.container = None
        self.video_stream = None
        self.gen = None
        self.current_frame = None
        self.status = VideoStatus.EMPTY
        self.hdr_still = False
        self.rgba_still = False

    def get_next_frame(self):
        if self.still:
            if self.current_frame is None:
                frame = next(self.gen)
            else:
                frame = self.current_frame
        else:
            try:
                if self.gen is not None:
                    frame = next(self.gen)
                else:
                    frame = None

            except StopIteration:
                frame = self.current_frame
                self.still = True
                # frame = self.seek_start()

            except Exception as e:
                # Transient decode error: don't crash, don't blank
                print(f"Decode error: {e} – freezing on last frame")

                frame = self.current_frame

        self.current_frame = frame
        return frame

    def seek_start(self):
        if not self.still and self.status in (
            VideoStatus.LOADING,
            VideoStatus.LOADED,
            VideoStatus.READY,
        ):
            frame = seek_to_time(
                self.container, self.video_stream, self.seek_start_seconds
            )
        else:
            frame = self.current_frame

        return frame


def seek_to_time(container, stream, target_time):
    # Convert time in seconds to PTS (presentation timestamp)
    try:
        target_pts = int(target_time / stream.time_base)

        # Seek to the nearest keyframe before the target time
        container.seek(target_pts, stream=stream, any_frame=False, backward=True)

        # Decode frames until you reach the exact target time
        for frame in container.decode(stream):
            if frame.pts is not None and frame.time >= target_time:
                return frame
    except:
        print("Seek failed")
    return None


def load_exr_still(path: str, video_data: VideoData):
    if OpenEXR is None or Imath is None:
        raise RuntimeError(
            "EXR support requires the OpenEXR Python package. Install 'OpenEXR'."
        )

    exr = OpenEXR.InputFile(path)
    header = exr.header()
    data_window = header["dataWindow"]
    width = data_window.max.x - data_window.min.x + 1
    height = data_window.max.y - data_window.min.y + 1

    pixel_type = Imath.PixelType(Imath.PixelType.FLOAT)
    channel_names = header["channels"].keys()

    def read_channel(name: str, fallback: float = 0.0) -> np.ndarray:
        if name in channel_names:
            raw = exr.channel(name, pixel_type)
            return np.frombuffer(raw, dtype=np.float32).reshape(height, width)
        return np.full((height, width), fallback, dtype=np.float32)

    rgba = np.stack(
        [
            read_channel("R"),
            read_channel("G"),
            read_channel("B"),
            read_channel("A", 1.0),
        ],
        axis=-1,
    ).astype(np.float32, copy=False)

    video_data.container = None
    video_data.video_stream = None
    video_data.gen = None
    video_data.width = width
    video_data.height = height
    video_data.frame_pix_format = VideoFrameFormat.RGB
    video_data.colour_space = VideoFrameColourSpace.RGB
    video_data.still = True
    video_data.hdr_still = True
    video_data.rgba_still = False
    video_data.current_frame = rgba
    video_data.status = VideoStatus.LOADED


def load_rgba_still(path: str, video_data: VideoData):
    surface = pygame.image.load(path).convert_alpha()
    width, height = surface.get_size()
    raw = pygame.image.tobytes(surface, "RGBA", False)
    rgba = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)

    video_data.container = None
    video_data.video_stream = None
    video_data.gen = None
    video_data.width = width
    video_data.height = height
    video_data.frame_pix_format = VideoFrameFormat.RGB
    video_data.colour_space = VideoFrameColourSpace.RGB
    video_data.still = True
    video_data.hdr_still = False
    video_data.rgba_still = True
    video_data.current_frame = rgba
    video_data.status = VideoStatus.LOADED


def load_video(path, video_data=VideoData()):
    print(f"Load video: {path}")

    try:
        if path.lower().endswith(".exr"):
            try:
                load_exr_still(path, video_data)
                return video_data
            except Exception as exr_error:
                print(f"[EXR] Falling back to PyAV for {path}: {exr_error}")
                container = av.open(path, format="image2")
                frame_pix_format = VideoFrameFormat.RGB
                still = True
        elif path.lower().endswith(".png"):
            load_rgba_still(path, video_data)
            return video_data
        elif path.lower().endswith((".jpg", ".jpeg", ".png")):
            container = av.open(path, format="image2")
            frame_pix_format = VideoFrameFormat.RGB
            still = True
        else:
            hwaccel = av.codec.hwaccel.HWAccel("drm", allow_software_fallback=True)
            container = av.open(path, hwaccel=hwaccel)
            # Default to NV12 then adjust if needed.
            frame_pix_format = VideoFrameFormat.NV12
            still = False

        video_stream = container.streams.video[0]
        colour_space = VideoFrameColourSpace.RGB

        if video_stream.format.is_rgb:
            frame_pix_format = VideoFrameFormat.RGB
            colour_space = VideoFrameColourSpace.RGB
        elif video_stream.format.name == "gray":
            frame_pix_format = VideoFrameFormat.GRAY
        elif "gbr" in video_stream.format.name and "pf32" in video_stream.format.name:
            frame_pix_format = VideoFrameFormat.RGB
            colour_space = VideoFrameColourSpace.RGB
        elif video_stream.format.name == "yuv420p":
            colour_space = VideoFrameColourSpace.BT601
        elif video_stream.format.name == "yuvj420p":
            frame_pix_format = VideoFrameFormat.YUVJ420p
            colour_space = VideoFrameColourSpace.BT709

        gen = container.decode(video=0)

        video_data.container = container
        video_data.video_stream = video_stream
        video_data.gen = gen
        video_data.width = video_stream.width
        video_data.height = video_stream.height
        video_data.frame_pix_format = frame_pix_format
        video_data.colour_space = colour_space
        video_data.still = still
        video_data.current_frame = video_data.seek_start()

        video_data.status = VideoStatus.LOADED

    except Exception as e:
        print(f"Error loading video {path}: {e}")
    return video_data


class VideoHandler:
    def __init__(self):
        self.current_index = 0
        self.video = []
        self.video.append(VideoData())
        self.video.append(VideoData())

    def load_video_async(self, path, video_data):
        video_data.status = VideoStatus.LOADING
        thread = threading.Thread(target=load_video, args=(path, video_data))
        thread.start()
