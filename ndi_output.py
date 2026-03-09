from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class NDIConfig:
    enabled: bool = False
    name: str = "pyPlay NDI"


class NDIOutput:
    def __init__(self, config: NDIConfig):
        self.config = config
        self.enabled = False
        self._ndi = None
        self._sender = None
        self._frame = None
        self._buffer: Optional[np.ndarray] = None

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

    def send_rgb_frame(self, rgb_frame: np.ndarray):
        if not self.enabled or self._ndi is None or self._sender is None or self._frame is None:
            return

        if rgb_frame.ndim != 3 or rgb_frame.shape[2] != 3:
            return

        h, w, _ = rgb_frame.shape
        if self._buffer is None or self._buffer.shape[0] != h or self._buffer.shape[1] != w:
            self._buffer = np.zeros((h, w, 4), dtype=np.uint8)

        # NDI expects BGRX in this configuration.
        self._buffer[..., 0] = rgb_frame[..., 2]  # B
        self._buffer[..., 1] = rgb_frame[..., 1]  # G
        self._buffer[..., 2] = rgb_frame[..., 0]  # R
        self._buffer[..., 3] = 255

        self._frame.data = self._buffer
        self._frame.xres = w
        self._frame.yres = h
        self._frame.FourCC = self._ndi.FOURCC_VIDEO_TYPE_BGRX
        self._frame.line_stride_in_bytes = w * 4
        self._frame.frame_rate_N = 25
        self._frame.frame_rate_D = 1

        self._ndi.send_send_video_v2(self._sender, self._frame)

    def close(self):
        if self._ndi is None:
            return
        try:
            if self._sender is not None:
                self._ndi.send_destroy(self._sender)
            self._ndi.destroy()
        except Exception:
            pass
