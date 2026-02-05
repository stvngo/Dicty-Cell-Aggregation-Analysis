"""
Convert a multi-frame TIFF movie to MP4/MOV video.

From README: "Each frame is 15 seconds" -> default FPS = 1/15 ≈ 0.067 fps
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import tifffile as tif


def tiff_to_video(
    tiff_file: str | Path,
    output_file: str | Path,
    *,
    fps: float = 1.0 / 15.0,  # 15 seconds per frame
    codec: str = "mp4v",
    normalize_16bit: bool = True,
) -> Path:
    """
    Convert a multi-frame TIFF stack to a video file (MP4/MOV).

    Args:
        tiff_file: Path to input TIFF stack
        output_file: Path to output video file
        fps: Frames per second (default: 1/15 ≈ 0.067 fps, based on README)
        codec: Video codec (default: 'mp4v', alternatives: 'avc1', 'h264', 'XVID')
        normalize_16bit: If True, normalize 16-bit images to 8-bit for video codecs

    Returns:
        Path to output video file
    """
    tiff_file = Path(tiff_file)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Read TIFF stack
    stack = tif.imread(tiff_file)
    print(f"Loaded TIFF: shape={stack.shape}, dtype={stack.dtype}")

    # Handle different stack shapes
    if stack.ndim == 3:
        # (T, Y, X) - grayscale
        n_frames, height, width = stack.shape
        is_color = False
    elif stack.ndim == 4:
        # (T, C, Y, X) or (T, Y, X, C)
        if stack.shape[1] in (1, 3, 4):
            # (T, C, Y, X)
            n_frames, n_channels, height, width = stack.shape
            is_color = n_channels > 1
        else:
            # (T, Y, X, C)
            n_frames, height, width, n_channels = stack.shape
            is_color = n_channels > 1
    else:
        raise ValueError(f"Expected 3D or 4D stack, got shape={stack.shape}")

    # Normalize 16-bit to 8-bit if needed
    if normalize_16bit and stack.dtype == np.uint16:
        print("Normalizing 16-bit to 8-bit...")
        stack = (stack / 256).astype(np.uint8)
    elif stack.dtype != np.uint8:
        # Convert other dtypes to uint8
        stack_min = stack.min()
        stack_max = stack.max()
        if stack_max > stack_min:
            stack = ((stack - stack_min) / (stack_max - stack_min) * 255).astype(np.uint8)
        else:
            stack = np.zeros_like(stack, dtype=np.uint8)

    # Initialize video writer
    fourcc = cv2.VideoWriter_fourcc(*codec)
    video_writer = cv2.VideoWriter(
        str(output_file), fourcc, fps, (width, height), is_color
    )

    if not video_writer.isOpened():
        raise RuntimeError(f"Failed to open video writer for {output_file}")

    # Write frames
    print(f"Writing {n_frames} frames at {fps} fps...")
    for i in range(n_frames):
        if stack.ndim == 3:
            frame = stack[i]
        elif stack.shape[1] in (1, 3, 4):
            # (T, C, Y, X)
            frame = stack[i].transpose(1, 2, 0) if is_color else stack[i, 0]
        else:
            # (T, Y, X, C)
            frame = stack[i]

        # Ensure frame is 2D (grayscale) or 3D (BGR)
        if is_color and frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif not is_color and frame.ndim == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

        video_writer.write(frame)

        if (i + 1) % 100 == 0:
            print(f"  Progress: {i+1}/{n_frames} frames")

    video_writer.release()
    print(f"Saved video: {output_file}")
    return output_file


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convert a multi-frame TIFF stack to MP4/MOV video."
    )
    p.add_argument("--input", "-i", required=True, help="Path to input TIFF movie")
    p.add_argument("--output", "-o", required=True, help="Path to output video file")

    p.add_argument(
        "--fps",
        type=float,
        default=1.0 / 15.0,
        help="Frames per second (default: 1/15 ≈ 0.067, based on README: 'Each frame is 15 seconds')",
    )
    p.add_argument(
        "--codec",
        type=str,
        default="mp4v",
        help="Video codec (default: 'mp4v', alternatives: 'avc1', 'h264', 'XVID')",
    )
    p.add_argument(
        "--no-normalize-16bit",
        action="store_true",
        help="Disable automatic 16-bit to 8-bit normalization",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    tiff_to_video(
        args.input,
        args.output,
        fps=args.fps,
        codec=args.codec,
        normalize_16bit=not args.no_normalize_16bit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
