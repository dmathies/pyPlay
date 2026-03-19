from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import time


@dataclass
class NDIConfig:
    enabled: bool = False
    name: str = "pyPlay NDI"
    width: int = 0
    height: int = 0
    fps: int = 25


class NDIOutput:
    def __init__(self, config: NDIConfig):
        self.config = config
        self.enabled = False
        self._ndi = None
        self._sender = None
        self._frame = None
        self._buffer: Optional[np.ndarray] = None
        self._buffer_shape: tuple[int, int] = (0, 0)
        self._send_count = 0
        self._last_debug_time = 0.0
        self._last_send_time = 0.0

        if not config.enabled:
            return

        try:
            import NDIlib as ndi  # type: ignore
        except Exception:
            print("[NDI] NDIlib not available; NDI output disabled.")
            return

        try:
            if not ndi.initialize():
                print("[NDI] Failed to initialize NDI; output disabled.")
                return

            send_create = ndi.SendCreate()
            send_create.ndi_name = config.name
            self._sender = ndi.send_create(send_create)
            if self._sender is None:
                print("[NDI] Failed to create NDI sender; output disabled.")
                ndi.destroy()
                return

            self._frame = ndi.VideoFrameV2()
            self._ndi = ndi
            self.enabled = True
            print(f"[NDI] Enabled sender '{config.name}'.")
        except Exception as ex:
            print(f"[NDI] Initialization error: {ex}")
            try:
                ndi.destroy()
            except Exception:
                pass

    @staticmethod
    def _resize_rgb_nearest(rgb_frame: np.ndarray, width: int, height: int) -> np.ndarray:
        src_h, src_w, _ = rgb_frame.shape
        if width <= 0 or height <= 0 or (src_w == width and src_h == height):
            return rgb_frame

        x_idx = np.linspace(0, src_w - 1, width, dtype=np.int32)
        y_idx = np.linspace(0, src_h - 1, height, dtype=np.int32)
        return rgb_frame[y_idx][:, x_idx]

    def send_rgb_frame(self, rgb_frame: Optional[np.ndarray]):
        if not self.enabled or self._ndi is None or self._sender is None or self._frame is None:
            return

        target_fps = max(1, int(self.config.fps))
        now = time.time()
        min_interval = 1.0 / target_fps
        if (now - self._last_send_time) < min_interval:
            return
        self._last_send_time = now

        if rgb_frame is None:
            return
        if rgb_frame.ndim != 3 or rgb_frame.shape[2] != 3:
            # print(f"[NDI] Ignoring frame with unexpected shape {rgb_frame.shape}")
            return

        src_h, src_w, _ = rgb_frame.shape
        if self.config.width > 0 and self.config.height > 0:
            rgb_frame = self._resize_rgb_nearest(rgb_frame, self.config.width, self.config.height)

        h, w, _ = rgb_frame.shape
        if self._buffer is None or self._buffer_shape != (h, w):
            self._buffer = np.zeros((h, w, 4), dtype=np.uint8)
            self._buffer_shape = (h, w)
            # print(f"[NDI] Allocated sender buffer {w}x{h} (source {src_w}x{src_h})")
            self._frame.xres = w
            self._frame.yres = h
            self._frame.FourCC = self._ndi.FOURCC_VIDEO_TYPE_BGRX
            self._frame.line_stride_in_bytes = w * 4
            self._frame.frame_rate_N = target_fps
            self._frame.frame_rate_D = 1
            self._frame.picture_aspect_ratio = w / h if h else 1.0
            self._frame.frame_format_type = self._ndi.FRAME_FORMAT_TYPE_PROGRESSIVE
            self._frame.timecode = self._ndi.SEND_TIMECODE_SYNTHESIZE
            self._frame.data = self._buffer

        # NDI expects BGRX in this configuration.
        self._buffer[..., 0] = rgb_frame[..., 2]  # B
        self._buffer[..., 1] = rgb_frame[..., 1]  # G
        self._buffer[..., 2] = rgb_frame[..., 0]  # R
        self._buffer[..., 3] = 255

        self._ndi.send_send_video_v2(self._sender, self._frame)
        self._send_count += 1

        now = time.time()
        if now - self._last_debug_time >= 1.0:
            # print(
            #     f"[NDI] Sending {self._send_count} fps-ish frames, "
            #     f"source={src_w}x{src_h} output={w}x{h}"
            # )
            self._send_count = 0
            self._last_debug_time = now

    def close(self):
        if self._ndi is None:
            return
        try:
            if self._sender is not None:
                self._ndi.send_destroy(self._sender)
            self._ndi.destroy()
        except Exception:
            pass
