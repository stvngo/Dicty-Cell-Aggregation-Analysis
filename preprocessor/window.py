"""
Preprocess a multi-frame TIFF movie by extracting a temporal + spatial window.

Expected TIFF shapes:
- (T, Y, X)
- (T, C, Y, X)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple

import tifffile as tif

def _validate_window(
    stack_shape: Tuple[int, ...],
    start_frame: int,
    end_frame: int,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
) -> None:
    if len(stack_shape) not in (3, 4):
        raise ValueError(
            f"Expected stack shape (T,Y,X) or (T,C,Y,X); got shape={stack_shape}"
        )

    t = stack_shape[0]
    y = stack_shape[-2]
    x = stack_shape[-1]

    if not (0 <= start_frame < end_frame <= t):
        raise ValueError(f"Invalid frame window: [{start_frame}, {end_frame}) for T={t}")
    if not (0 <= start_row < end_row <= y):
        raise ValueError(f"Invalid row window: [{start_row}, {end_row}) for Y={y}")
    if not (0 <= start_col < end_col <= x):
        raise ValueError(f"Invalid col window: [{start_col}, {end_col}) for X={x}")


def extract_window(
    tiff_file: str | Path,
    output_file: str | Path,
    *,
    start_frame: int = 10,
    end_frame: int = 20,
    start_row: int = 100,
    end_row: int = 300,
    start_col: int = 150,
    end_col: int = 350,
    use_memmap: bool = True,
) -> Path:
    """
    Extract a combined temporal + spatial subset and save it as a new TIFF stack.
    """
    tiff_file = Path(tiff_file)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    stack = tif.memmap(tiff_file) if use_memmap else tif.imread(tiff_file)
    _validate_window(
        stack.shape, start_frame, end_frame, start_row, end_row, start_col, end_col
    )

    if stack.ndim == 3:
        # (T, Y, X)
        subset = stack[start_frame:end_frame, start_row:end_row, start_col:end_col]
    else:
        # (T, C, Y, X)
        subset = stack[start_frame:end_frame, :, start_row:end_row, start_col:end_col]

    tif.imwrite(output_file, subset)
    return output_file


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract a temporal+spatial window from a multi-frame TIFF."
    )
    p.add_argument("--input", "-i", required=True, help="Path to input TIFF movie")
    p.add_argument("--output", "-o", required=True, help="Path to output TIFF movie")

    p.add_argument("--start-frame", type=int, default=10)
    p.add_argument("--end-frame", type=int, default=20)
    p.add_argument("--start-row", type=int, default=100)
    p.add_argument("--end-row", type=int, default=300)
    p.add_argument("--start-col", type=int, default=150)
    p.add_argument("--end-col", type=int, default=350)

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
