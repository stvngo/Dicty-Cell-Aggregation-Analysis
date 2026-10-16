"""
Stack sorted JPG frames into a single multi-page TIFF.

Example:
  python preprocessor/jpgs_to_tiff.py \\
    --input-dir roboflow/images/results/2026-05-16_232640 \\
    --output roboflow/images/results/2026-05-16_232640/stack.tif
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import tifffile as tif
from PIL import Image


def _frame_index(path: Path) -> int:
    m = re.search(r"_C(\d+)\.jpe?g$", path.name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"_(\d+)\.jpe?g$", path.name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


def jpgs_to_tiff(input_dir: Path, output_path: Path) -> int:
    jpgs = sorted(
        [p for p in input_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"}],
        key=_frame_index,
    )
    if not jpgs:
        raise SystemExit(f"No JPG files in {input_dir}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tif.TiffWriter(output_path, bigtiff=True) as writer:
        for i, path in enumerate(jpgs):
            frame = np.asarray(Image.open(path))
            if frame.ndim == 2:
                pass
            elif frame.ndim == 3 and frame.shape[2] in (3, 4):
                frame = frame[..., :3]  # drop alpha if present
            else:
                raise ValueError(f"Unexpected shape {frame.shape} for {path.name}")
            writer.write(frame, compression="zlib")
            if (i + 1) % 200 == 0 or i + 1 == len(jpgs):
                print(f"  Wrote {i + 1}/{len(jpgs)}: {path.name}")

    return len(jpgs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stack JPGs into one multi-page TIFF.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .tif path (default: <input-dir>/stack.tif)",
    )
    args = parser.parse_args()
    input_dir = args.input_dir.resolve()
    output_path = (args.output or input_dir / "stack.tif").resolve()

    print(f"Input:  {input_dir}")
    print(f"Output: {output_path}")
    n = jpgs_to_tiff(input_dir, output_path)
    print(f"Done. {n} frames -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
