from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyp_image import read_pyp_image, write_exr_rgba


def iter_pyp_files(inputs: list[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            pattern = "**/*.pyp" if recursive else "*.pyp"
            files.extend(sorted(path.glob(pattern)))
        elif path.suffix.lower() == ".pyp":
            files.append(path)
    return files


def build_output_path(source: Path, output: Path | None) -> Path:
    if output is None:
        return source.with_suffix(".exr")
    if output.exists() and output.is_dir():
        return output / source.with_suffix(".exr").name
    if output.suffix.lower() == ".exr":
        return output
    return output / source.with_suffix(".exr").name


def convert_file(source: Path, destination: Path, overwrite: bool) -> None:
    if destination.exists() and not overwrite:
        print(f"skip  {destination} (already exists)")
        return

    image = read_pyp_image(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_exr_rgba(destination, image.pixels)
    channels = image.pixels.shape[2] if image.pixels.ndim == 3 else 1
    print(f"write {source} -> {destination} ({image.width}x{image.height}, {channels}ch)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert pyPlay's .pyp float16 format to EXR stills."
    )
    parser.add_argument("inputs", nargs="+", help="PYP files or directories to convert.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .exr file or destination directory. Defaults to next to each source file.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Search input directories recursively for .pyp files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .exr files.",
    )
    args = parser.parse_args()

    sources = iter_pyp_files(args.inputs, args.recursive)
    if not sources:
        parser.error("No .pyp files found in the provided inputs.")

    if args.output and len(sources) > 1 and args.output.suffix.lower() == ".exr":
        parser.error("A single .exr output file can only be used with one source PYP.")

    for source in sources:
        destination = build_output_path(source, args.output)
        convert_file(
            source,
            destination,
            overwrite=args.overwrite,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
