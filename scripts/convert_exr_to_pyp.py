from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyp_image import read_exr_rgba, write_pyp_image


def iter_exr_files(inputs: list[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            pattern = "**/*.exr" if recursive else "*.exr"
            files.extend(sorted(path.glob(pattern)))
        elif path.suffix.lower() == ".exr":
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


def convert_file(source: Path, destination: Path, overwrite: bool) -> None:
    if destination.exists() and not overwrite:
        print(f"skip  {destination} (already exists)")
        return

    image = read_exr_rgba(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_pyp_image(destination, image.pixels[..., :3], image.content_bounds_uv)
    print(f"write {source} -> {destination} ({image.width}x{image.height})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert EXR stills to pyPlay's preconverted .pyp RGBA16F format."
    )
    parser.add_argument("inputs", nargs="+", help="EXR files or directories to convert.")
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
        help="Search input directories recursively for .exr files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .pyp files.",
    )
    args = parser.parse_args()

    sources = iter_exr_files(args.inputs, args.recursive)
    if not sources:
        parser.error("No .exr files found in the provided inputs.")

    if args.output and len(sources) > 1 and args.output.suffix.lower() == ".pyp":
        parser.error("A single .pyp output file can only be used with one source EXR.")

    for source in sources:
        destination = build_output_path(source, args.output)
        convert_file(source, destination, overwrite=args.overwrite)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
