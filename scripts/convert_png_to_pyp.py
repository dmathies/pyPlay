from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import pygame

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyp_image import write_pyp_image


def iter_png_files(inputs: list[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            pattern = "**/*.png" if recursive else "*.png"
            files.extend(sorted(path.glob(pattern)))
        elif path.suffix.lower() == ".png":
            files.append(path)
    return files


def build_output_path(source: Path, output: Path | None) -> Path:
    if output is None:
        return source.with_suffix(".pyp")
    if output.exists() and output.is_dir():
        return output / source.with_suffix(".pyp").name
    if output.suffix.lower() == ".pyp":
        return output
    return output / source.with_suffix(".pyp").name


def read_png_rgba(source: Path) -> np.ndarray:
    surface = pygame.image.load(str(source))
    width, height = surface.get_size()
    raw = pygame.image.tobytes(surface, "RGBA", False)
    rgba = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
    return rgba.astype(np.float32) / 255.0


def convert_file(
    source: Path,
    destination: Path,
    overwrite: bool,
    include_alpha: bool,
    black_threshold: float,
) -> None:
    if destination.exists() and not overwrite:
        print(f"skip  {destination} (already exists)")
        return

    rgba = read_png_rgba(source)
    pixels = rgba if include_alpha else rgba[..., :3]

    destination.parent.mkdir(parents=True, exist_ok=True)
    write_pyp_image(destination, pixels, black_threshold=black_threshold)

    height, width = pixels.shape[:2]
    channels = pixels.shape[2] if pixels.ndim == 3 else 1
    print(f"write {source} -> {destination} ({width}x{height}, {channels}ch)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert PNG stills to pyPlay's preconverted .pyp float16 format."
    )
    parser.add_argument("inputs", nargs="+", help="PNG files or directories to convert.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .pyp file or destination directory. Defaults to next to each source file.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Search input directories recursively for .png files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .pyp files.",
    )
    parser.add_argument(
        "--no-alpha",
        action="store_true",
        help="Store RGB only in output .pyp, dropping PNG alpha.",
    )
    parser.add_argument(
        "--black-threshold",
        type=float,
        default=1e-6,
        help="Threshold used when detecting non-black pixels for content bounds metadata.",
    )
    args = parser.parse_args()

    if args.black_threshold < 0.0:
        parser.error("--black-threshold must be non-negative.")

    sources = iter_png_files(args.inputs, args.recursive)
    if not sources:
        parser.error("No .png files found in the provided inputs.")

    if args.output and len(sources) > 1 and args.output.suffix.lower() == ".pyp":
        parser.error("A single .pyp output file can only be used with one source PNG.")

    pygame.image.init()
    try:
        for source in sources:
            destination = build_output_path(source, args.output)
            convert_file(
                source,
                destination,
                overwrite=args.overwrite,
                include_alpha=not args.no_alpha,
                black_threshold=args.black_threshold,
            )
    finally:
        pygame.image.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
