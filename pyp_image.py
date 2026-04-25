from __future__ import annotations

from dataclasses import dataclass
import struct
from pathlib import Path

import numpy as np

try:
    import OpenEXR  # type: ignore
    import Imath  # type: ignore
except ImportError:
    OpenEXR = None
    Imath = None


PYP_MAGIC = b"PYP1"
PYP_DTYPE_FLOAT16 = 1
PYP_CHANNELS_RGB = 3
PYP_HEADER_STRUCT = struct.Struct("<4sIIII4f")


@dataclass(frozen=True)
class PypImage:
    width: int
    height: int
    pixels: np.ndarray
    content_bounds_uv: tuple[float, float, float, float]


def find_content_bounds_uv(
    image: np.ndarray, threshold: float = 1e-6
) -> tuple[float, float, float, float]:
    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        return (0.0, 0.0, 1.0, 1.0)

    if image.ndim < 3:
        mask = np.abs(image) > threshold
    else:
        rgb_mask = np.any(np.abs(image[..., : min(3, image.shape[2])]) > threshold, axis=-1)
        if image.shape[2] >= 4:
            alpha_mask = np.abs(image[..., 3]) > threshold
            mask = rgb_mask | alpha_mask
        else:
            mask = rgb_mask

    non_zero = np.argwhere(mask)
    if non_zero.size == 0:
        return (0.0, 0.0, 1.0, 1.0)

    min_y, min_x = non_zero.min(axis=0)
    max_y, max_x = non_zero.max(axis=0)

    return (
        float(min_x) / float(width),
        float(min_y) / float(height),
        float(max_x + 1) / float(width),
        float(max_y + 1) / float(height),
    )


def read_exr_rgba(path: str | Path) -> PypImage:
    if OpenEXR is None or Imath is None:
        raise RuntimeError(
            "EXR support requires the OpenEXR Python package. Install 'OpenEXR'."
        )

    exr = OpenEXR.InputFile(str(path))
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

    return PypImage(
        width=width,
        height=height,
        pixels=rgba,
        content_bounds_uv=find_content_bounds_uv(rgba),
    )


def write_pyp_image(
    path: str | Path,
    rgb: np.ndarray,
    content_bounds_uv: tuple[float, float, float, float] | None = None,
) -> None:
    if rgb.ndim != 3 or rgb.shape[2] != PYP_CHANNELS_RGB:
        raise ValueError("PYP images must be HxWx3 RGB arrays.")

    height, width, _ = rgb.shape
    bounds = content_bounds_uv or find_content_bounds_uv(rgb)
    rgb16 = np.ascontiguousarray(rgb.astype(np.float16, copy=False))

    header = PYP_HEADER_STRUCT.pack(
        PYP_MAGIC,
        width,
        height,
        PYP_CHANNELS_RGB,
        PYP_DTYPE_FLOAT16,
        *bounds,
    )
    Path(path).write_bytes(header + rgb16.tobytes())


def read_pyp_image(path: str | Path) -> PypImage:
    raw = Path(path).read_bytes()
    if len(raw) < PYP_HEADER_STRUCT.size:
        raise ValueError(f"PYP file is too small: {path}")

    magic, width, height, channels, data_type, *bounds = PYP_HEADER_STRUCT.unpack(
        raw[: PYP_HEADER_STRUCT.size]
    )
    if magic != PYP_MAGIC:
        raise ValueError(f"Unsupported PYP magic in {path!s}")
    if channels != PYP_CHANNELS_RGB:
        raise ValueError(f"Unsupported PYP channel count {channels} in {path!s}")
    if data_type != PYP_DTYPE_FLOAT16:
        raise ValueError(f"Unsupported PYP data type {data_type} in {path!s}")

    expected_bytes = width * height * channels * np.dtype(np.float16).itemsize
    payload = raw[PYP_HEADER_STRUCT.size :]
    if len(payload) != expected_bytes:
        raise ValueError(
            f"PYP payload size mismatch in {path!s}: expected {expected_bytes}, got {len(payload)}"
        )

    rgb = np.frombuffer(payload, dtype=np.float16).reshape(height, width, channels)
    return PypImage(
        width=width,
        height=height,
        pixels=np.ascontiguousarray(rgb),
        content_bounds_uv=tuple(float(v) for v in bounds),
    )
