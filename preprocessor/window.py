"""
Preprocess a multi-frame TIFF movie by extracting a temporal + spatial window.

Expected TIFF shapes:
- (T, Y, X)
- (T, C, Y, X)
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Tuple

import tifffile as tif

def _validate_window(
    stack_shape: Tuple[int, ...],
    start_frame: int | None,
    end_frame: int | None,
    start_row: int | None,
    end_row: int | None,
    start_col: int | None,
    end_col: int | None,
) -> None:
    if len(stack_shape) not in (3, 4):
        raise ValueError(
            f"Expected stack shape (T,Y,X) or (T,C,Y,X); got shape={stack_shape}"
        )

    t = stack_shape[0]
    y = stack_shape[-2]
    x = stack_shape[-1]

    # Validate frame window (None means "to the end" or "from the start")
    if start_frame is not None and not (0 <= start_frame < t):
        raise ValueError(f"Invalid start_frame: {start_frame} for T={t}")
    if end_frame is not None:
        if start_frame is not None and not (start_frame < end_frame <= t):
            raise ValueError(f"Invalid frame window: [{start_frame}, {end_frame}) for T={t}")
        elif not (0 < end_frame <= t):
            raise ValueError(f"Invalid end_frame: {end_frame} for T={t}")
    
    # Validate row window
    if start_row is not None and not (0 <= start_row < y):
        raise ValueError(f"Invalid start_row: {start_row} for Y={y}")
    if end_row is not None:
        if start_row is not None and not (start_row < end_row <= y):
            raise ValueError(f"Invalid row window: [{start_row}, {end_row}) for Y={y}")
        elif not (0 < end_row <= y):
            raise ValueError(f"Invalid end_row: {end_row} for Y={y}")
    
    # Validate col window
    if start_col is not None and not (0 <= start_col < x):
        raise ValueError(f"Invalid start_col: {start_col} for X={x}")
    if end_col is not None:
        if start_col is not None and not (start_col < end_col <= x):
            raise ValueError(f"Invalid col window: [{start_col}, {end_col}) for X={x}")
        elif not (0 < end_col <= x):
            raise ValueError(f"Invalid end_col: {end_col} for X={x}")


def _generate_output_filename(
    start_frame: int | None,
    end_frame: int | None,
    start_row: int | None,
    end_row: int | None,
    start_col: int | None,
    end_col: int | None,
    output_dir: Path | None = None,
) -> Path:
    """
    Generate output filename in format: YYYYMMDD_HHMMSS_subset_f{start}-{end}_x{start}-{end}_y{start}-{end}.tif
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parts = [timestamp, "subset"]
    
    # Add frame range if specified
    if start_frame is not None or end_frame is not None:
        if start_frame is not None and end_frame is not None:
            parts.append(f"f{start_frame}-{end_frame}")
        elif start_frame is not None:
            parts.append(f"f{start_frame}-end")
        elif end_frame is not None:
            parts.append(f"f0-{end_frame}")
    
    # Add column range if specified
    if start_col is not None or end_col is not None:
        if start_col is not None and end_col is not None:
            parts.append(f"x{start_col}-{end_col}")
        elif start_col is not None:
            parts.append(f"x{start_col}-end")
        elif end_col is not None:
            parts.append(f"x0-{end_col}")
    
    # Add row range if specified
    if start_row is not None or end_row is not None:
        if start_row is not None and end_row is not None:
            parts.append(f"y{start_row}-{end_row}")
        elif start_row is not None:
            parts.append(f"y{start_row}-end")
        elif end_row is not None:
            parts.append(f"y0-{end_row}")
    
    filename = "_".join(parts) + ".tif"
    
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / filename
    return Path(filename)


def extract_window(
    tiff_file: str | Path,
    output_file: str | Path | None = None,
    *,
    start_frame: int | None = None,
    end_frame: int | None = None,
    start_row: int | None = None,
    end_row: int | None = None,
    start_col: int | None = None,
    end_col: int | None = None,
    use_memmap: bool = True,
) -> Path:
    """
    Extract a combined temporal + spatial subset and save it as a new TIFF stack.
    """
    tiff_file = Path(tiff_file)
    
    # Auto-generate output filename if not provided
    if output_file is None:
        output_file = _generate_output_filename(
            start_frame, end_frame, start_row, end_row, start_col, end_col,
            output_dir=Path("data/subsets")
        )
    else:
        output_file = Path(output_file)
    
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # stack = tif.memmap(tiff_file) if use_memmap else tif.imread(tiff_file)
    stack = tif.imread(tiff_file)
    _validate_window(
        stack.shape, start_frame, end_frame, start_row, end_row, start_col, end_col
    )

    if stack.ndim == 3:
        subset = stack[start_frame:end_frame, start_row:end_row, start_col:end_col]
    else:
        subset = stack[start_frame:end_frame, :, start_row:end_row, start_col:end_col]

    tif.imwrite(output_file, subset)
    return output_file


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract a temporal+spatial window from a multi-frame TIFF."
    )
    p.add_argument("--input", "-i", required=True, help="Path to input TIFF movie")
    p.add_argument(
        "--output", "-o", default=None,
        help="Path to output TIFF movie (auto-generated if not provided)"
    )

    p.add_argument("--start-frame", type=int, default=None)
    p.add_argument("--end-frame", type=int, default=None)
    p.add_argument("--start-row", type=int, default=None)
    p.add_argument("--end-row", type=int, default=None)
    p.add_argument("--start-col", type=int, default=None)
    p.add_argument("--end-col", type=int, default=None)

    p.add_argument(
        "--no-memmap",
        action="store_true",
        help="Disable memory mapping (loads full TIFF into RAM).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    extract_window(
        args.input,
        args.output,
        start_frame=args.start_frame,
        end_frame=args.end_frame,
        start_row=args.start_row,
        end_row=args.end_row,
        start_col=args.start_col,
        end_col=args.end_col,
        use_memmap=not args.no_memmap,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
