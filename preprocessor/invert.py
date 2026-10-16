"""
Pixel-invert a folder of 8-bit frames (e.g. c1: white background, dark cells
-> dark background, bright cells, matching c0 / timeconvol).

Lossless PNG input is preferred; output format follows --ext.

Example:
  python preprocessor/invert.py \\
    --input-dir data/png/c1 \\
    --output-dir data/jpg/c1_inverted --ext .jpg
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def invert_frame(src: Path, dst: Path, quality: int) -> None:
    img = np.asarray(Image.open(src).convert("L"))
    out = Image.fromarray(255 - img)
    if dst.suffix.lower() in {".jpg", ".jpeg"}:
        out.save(dst, quality=quality)
    else:
        out.save(dst)


def invert_folder(input_dir: Path, output_dir: Path, ext: str, quality: int, overwrite: bool) -> int:
    frames = sorted(p for p in input_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not frames:
        raise SystemExit(f"No images found in {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    for src in frames:
        dst = output_dir / (src.stem + ext)
        if overwrite or not dst.exists():
            jobs.append((src, dst))

    with ThreadPoolExecutor() as pool:
        list(pool.map(lambda job: invert_frame(*job, quality), jobs))

    print(f"Inverted {len(jobs)} / {len(frames)} frames -> {output_dir}")
    return len(jobs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pixel-invert a folder of 8-bit frames.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/png/c1"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/jpg/c1_inverted"))
    parser.add_argument("--ext", default=".jpg", help="Output extension (.jpg or .png).")
    parser.add_argument("--quality", type=int, default=95, help="JPEG quality.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    invert_folder(args.input_dir, args.output_dir, args.ext, args.quality, args.overwrite)


if __name__ == "__main__":
    main()
