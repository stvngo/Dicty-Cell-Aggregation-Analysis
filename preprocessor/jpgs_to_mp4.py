"""
Stack sorted JPG frames into an MP4 video.

Example:
  python preprocessor/jpgs_to_mp4.py \\
    --input-dir roboflow/images/results/2026-05-16_232640 \\
    --output roboflow/images/results/2026-05-16_232640/stack.mp4

  # Browser-playable H.264 at 60 fps with a frame / assay-time stamp
  python preprocessor/jpgs_to_mp4.py --input-dir roboflow/images/results/2026-05-16 \\
    --output assets/video/roboflow_waves_2026-05-16_60fps.mp4 --fps 60 --codec avc1 --label
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def _frame_index(path: Path) -> int:
    m = re.search(r"_C(\d+)\.jpe?g$", path.name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"_(\d+)\.jpe?g$", path.name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


def _stamp(frame: np.ndarray, index: int, seconds_per_frame: float) -> None:
    """Draw 'frame N  t = Hh MMm' in the bottom-left corner, in place."""
    minutes = int(index * seconds_per_frame // 60)
    text = f"frame {index}  t = {minutes // 60}h {minutes % 60:02d}m"
    org = (8, frame.shape[0] - 10)
    white = 255 if frame.ndim == 2 else (255, 255, 255)
    black = 0 if frame.ndim == 2 else (0, 0, 0)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.5, black, 3, cv2.LINE_AA)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.5, white, 1, cv2.LINE_AA)


def jpgs_to_mp4(
    input_dir: Path,
    output_path: Path,
    *,
    fps: float = 1.0 / 15.0,
    codec: str = "mp4v",
    label: bool = False,
    seconds_per_frame: float = 15.0,
) -> int:
    jpgs = sorted(
        [p for p in input_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"}],
        key=_frame_index,
    )
    if not jpgs:
        raise SystemExit(f"No JPG files in {input_dir}")

    first = np.asarray(Image.open(jpgs[0]))
    if first.ndim == 2:
        height, width = first.shape
        is_color = False
    elif first.ndim == 3:
        height, width = first.shape[:2]
        is_color = True
    else:
        raise ValueError(f"Unexpected shape {first.shape}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*codec),
        fps,
        (width, height),
        is_color,
    )
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open VideoWriter for {output_path}")

    for i, path in enumerate(jpgs):
        frame = np.asarray(Image.open(path))
        if is_color:
            if frame.ndim == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            else:
                frame = cv2.cvtColor(frame[..., :3], cv2.COLOR_RGB2BGR)
        elif frame.ndim == 3:
            frame = cv2.cvtColor(frame[..., :3], cv2.COLOR_RGB2GRAY)
        if label:
            frame = np.ascontiguousarray(frame)
            _stamp(frame, _frame_index(path), seconds_per_frame)
        writer.write(frame)
        if (i + 1) % 200 == 0 or i + 1 == len(jpgs):
            print(f"  Wrote {i + 1}/{len(jpgs)}: {path.name}")

    writer.release()
    return len(jpgs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Encode sorted JPGs as MP4.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .mp4 path (default: <input-dir>/stack.mp4)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=1.0 / 15.0,
        help="Playback FPS (default 1/15 ≈ one frame per 15 s of assay time)",
    )
    parser.add_argument(
        "--codec",
        type=str,
        default="mp4v",
        help="FourCC codec (default mp4v; avc1 = H.264, plays in browsers / GitHub)",
    )
    parser.add_argument(
        "--label",
        action="store_true",
        help="Stamp each frame with its index and assay time (15 s per frame).",
    )
    args = parser.parse_args()
    input_dir = args.input_dir.resolve()
    output_path = (args.output or input_dir / "stack.mp4").resolve()

    print(f"Input:  {input_dir}")
    print(f"Output: {output_path}")
    print(f"FPS:    {args.fps}")
    n = jpgs_to_mp4(input_dir, output_path, fps=args.fps, codec=args.codec, label=args.label)
    print(f"Done. {n} frames -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
