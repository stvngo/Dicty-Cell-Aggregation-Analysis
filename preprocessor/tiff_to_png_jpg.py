"""
Convert TIFF files in data/raw/ to PNG and JPG copies.

Outputs (per source TIFF, under channel or stem-named subfolders):
- data/png/c0/<same-name>_0000.png
- data/jpg/c0/<same-name>_0000.jpg
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import tifffile as tif
from PIL import Image


def _to_uint8(image: np.ndarray) -> np.ndarray:
    """Convert image array to uint8 with robust per-frame normalization."""
    if image.dtype == np.uint8:
        return image

    if np.issubdtype(image.dtype, np.integer):
        if np.iinfo(image.dtype).max <= 255:
            return image.astype(np.uint8)

        # For 12/16-bit microscopy data, scaling by dtype max (e.g., 65535)
        # can make outputs nearly black when the true signal occupies a narrow band.
        image_f = image.astype(np.float32)
        low, high = np.percentile(image_f, [1.0, 99.5])
        if high <= low:
            low = float(np.min(image_f))
            high = float(np.max(image_f))
        if high <= low:
            return np.zeros_like(image, dtype=np.uint8)
        clipped = np.clip(image_f, low, high)
        scaled = (clipped - low) / (high - low)
        return (scaled * 255).astype(np.uint8)

    if np.issubdtype(image.dtype, np.floating):
        image = np.nan_to_num(image, nan=0.0, posinf=1.0, neginf=0.0)
        min_val = float(np.min(image))
        max_val = float(np.max(image))
        if max_val <= min_val:
            return np.zeros_like(image, dtype=np.uint8)
        scaled = (image - min_val) / (max_val - min_val)
        return (scaled * 255).astype(np.uint8)

    return image.astype(np.uint8)


def _prepare_image(array: np.ndarray) -> np.ndarray:
    """Convert a single TIFF frame array to a PIL-friendly image array."""
    # Drop singleton channel dimensions like (1, H, W) or (H, W, 1).
    if array.ndim == 3:
        if array.shape[0] == 1:
            array = array[0]
        elif array.shape[-1] == 1:
            array = array[..., 0]

    array = _to_uint8(array)

    # If channel-first RGB/RGBA, convert to channel-last.
    if array.ndim == 3 and array.shape[0] in (3, 4) and array.shape[-1] not in (3, 4):
        array = np.moveaxis(array, 0, -1)

    return array


def _output_subdir_for_tif_stem(tif_stem: str) -> str:
    """
    Map TIFF filename stem to an output subfolder under png/ and jpg/.

    Microscopy stacks ending in _C0 / _C1 → c0 / c1. Other names use a safe slug
    (e.g. highdensity_timeconvol → highdensity_timeconvol).
    """
    m = re.search(r"_C(\d+)$", tif_stem)
    if m:
        return f"c{m.group(1)}"
    safe = re.sub(r"[^\w\-]+", "_", tif_stem).strip("_")
    return safe or "other"


def convert_tiffs(
    raw_dir: str | Path = "data/raw",
    output_root: str | Path = "data",
    png_subdir: str = "png",
    jpg_subdir: str = "jpg",
    recursive: bool = True,
) -> tuple[int, int]:
    """
    Convert TIFF files under raw_dir into PNG and JPG files.

    Returns:
        (converted_frames_count, failed_files_count)
    """
    raw_dir = Path(raw_dir)
    output_root = Path(output_root)
    png_dir = output_root / png_subdir
    jpg_dir = output_root / jpg_subdir
    png_dir.mkdir(parents=True, exist_ok=True)
    jpg_dir.mkdir(parents=True, exist_ok=True)

    pattern = "**/*" if recursive else "*"
    tiff_files = [
        p
        for p in raw_dir.glob(pattern)
        if p.is_file() and p.suffix.lower() in {".tif", ".tiff"}
    ]

    # Avoid re-processing files from output folders if user reruns in future.
    tiff_files = [p for p in tiff_files if png_subdir not in p.parts and jpg_subdir not in p.parts]

    converted = 0
    failed = 0
    print(f"Scanning TIFFs in: {raw_dir.resolve()}")
    print(f"Writing PNG to: {png_dir.resolve()}/<c0|c1|…>/")
    print(f"Writing JPG to: {jpg_dir.resolve()}/<c0|c1|…>/")
    print(f"Found {len(tiff_files)} TIFF file(s).")

    for tif_path in sorted(tiff_files):
        try:
            subdir = _output_subdir_for_tif_stem(tif_path.stem)
            png_sub = png_dir / subdir
            jpg_sub = jpg_dir / subdir
            png_sub.mkdir(parents=True, exist_ok=True)
            jpg_sub.mkdir(parents=True, exist_ok=True)

            with tif.TiffFile(tif_path) as tif_file:
                pages = tif_file.pages
                n_pages = len(pages)
                digits = max(4, len(str(n_pages - 1 if n_pages else 0)))
                print(f"[TIFF] {tif_path.name}: {n_pages} frame(s) -> {subdir}/")

                for idx, page in enumerate(pages):
                    arr = _prepare_image(page.asarray())
                    image = Image.fromarray(arr)

                    if image.mode == "RGBA":
                        jpg_image = image.convert("RGB")
                    elif image.mode not in ("L", "RGB"):
                        jpg_image = image.convert("RGB")
                    else:
                        jpg_image = image

                    frame_name = f"{tif_path.stem}_{idx:0{digits}d}"
                    png_out = png_sub / f"{frame_name}.png"
                    jpg_out = jpg_sub / f"{frame_name}.jpg"
                    image.save(png_out)
                    jpg_image.save(jpg_out, quality=95)
                    converted += 1

                    if (idx + 1) % 200 == 0 or idx + 1 == n_pages:
                        print(
                            f"  Progress {tif_path.name}: {idx + 1}/{n_pages} frames"
                        )

            print(f"[OK] Finished {tif_path.name}")
        except Exception as exc:  # pragma: no cover - CLI script safety
            failed += 1
            print(f"[FAIL] {tif_path}: {exc}")

    return converted, failed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert TIFF files in data/raw to data/png/<cN|stem>/ and data/jpg/<cN|stem>/."
        )
    )
    parser.add_argument(
        "--raw-dir",
        default="data/raw",
        help="Input folder containing TIFF files (default: data/raw)",
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Output root folder (default: data)",
    )
    parser.add_argument(
        "--non-recursive",
        action="store_true",
        help="Only scan the top-level raw directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    converted, failed = convert_tiffs(
        raw_dir=args.raw_dir,
        output_root=args.output_dir,
        recursive=not args.non_recursive,
    )
    print(f"Done. Converted: {converted}, Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
