"""
Frame sources for the 3D lift.

Each source is one rendering of the "Capture 4 - Position 1" movie that has
bright cells on a dark background (c1 is inverted on load), plus the TrackMate
spots table that was tracked on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]

PIXEL_TO_MICRON = 3.731309
SECONDS_PER_FRAME = 15
N_FRAMES = 4000
FRAME_SIZE = 512


@dataclass(frozen=True)
class Source:
    name: str
    frames_dir: Path          # lossless frames read by the decomposition
    invert: bool              # invert on load (c1 has dark cells on white)
    viewer_dir: Path          # already-bright-on-dark JPGs shown by the viewer
    spots_csv: Path           # TrackMate spots tracked on this source
    spots_in_microns: bool    # trial_4 exports are calibrated, trial_5 are pixels
    spots_time_reversed: bool  # trial_5 was tracked on a time-reversed stack
    flatten_radius: int       # background opening radius (px); > largest aggregate radius


SOURCES: dict[str, Source] = {
    "c1_inverted": Source(
        name="c1_inverted",
        frames_dir=REPO_ROOT / "data/png/c1",
        invert=True,
        viewer_dir=REPO_ROOT / "data/jpg/c1_inverted",
        spots_csv=REPO_ROOT / "results/trial_4/Capture 4 - Position 1_XY1694558559_Z0_T0000_spots.csv",
        spots_in_microns=True,
        spots_time_reversed=False,
        flatten_radius=48,
    ),
    "timeconvol": Source(
        name="timeconvol",
        frames_dir=REPO_ROOT / "data/png/highdensity_timeconvol",
        invert=False,
        viewer_dir=REPO_ROOT / "data/jpg/highdensity_timeconvol",
        spots_csv=REPO_ROOT / "results/trial_5/highdensity_spots.csv",
        spots_in_microns=False,
        spots_time_reversed=True,
        flatten_radius=48,
    ),
}

_FRAME_RE = re.compile(r"_(\d+)\.(?:png|jpe?g)$", re.IGNORECASE)


def frame_index(path: Path) -> int:
    m = _FRAME_RE.search(path.name)
    if not m:
        raise ValueError(f"No trailing frame index in {path.name}")
    return int(m.group(1))


def frame_paths(directory: Path) -> list[Path]:
    """Frames sorted by trailing index; position in the list == frame number."""
    paths = [p for p in directory.iterdir() if _FRAME_RE.search(p.name)]
    paths.sort(key=frame_index)
    return paths


def load_frame(source: Source, path: Path) -> np.ndarray:
    """Raw frame as float32 in [0, 1], bright cells on dark background."""
    img = np.asarray(Image.open(path).convert("L"), dtype=np.float32) / 255.0
    return 1.0 - img if source.invert else img


def estimate_background(img: np.ndarray, radius: int, scale: int = 4) -> np.ndarray:
    """
    Smooth illumination/background estimate via a coarse grey opening.

    The opening removes anything narrower than ~2*radius (cells, streams and
    aggregates), leaving the vignette of the inverted c1 movie. It runs on a
    downsampled copy for speed.
    """
    h, w = img.shape
    small = cv2.resize(img, (w // scale, h // scale), interpolation=cv2.INTER_AREA)
    r = max(1, radius // scale)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    # Pad by reflection so the opening does not drag in the image border.
    padded = cv2.copyMakeBorder(small, r, r, r, r, cv2.BORDER_REFLECT)
    opened = cv2.morphologyEx(padded, cv2.MORPH_OPEN, kernel)[r:-r, r:-r]
    opened = cv2.GaussianBlur(opened, (0, 0), sigmaX=r / 2)
    return cv2.resize(opened, (w, h), interpolation=cv2.INTER_LINEAR)


def flatten(img: np.ndarray, radius: int) -> np.ndarray:
    """Background-subtracted frame, clipped at 0."""
    return np.clip(img - estimate_background(img, radius), 0.0, None)


def valid_mask(source: Source, paths: list[Path], n_samples: int = 24) -> np.ndarray:
    """
    Pixels that are inside the illuminated field for the whole movie.

    The inverted c1 movie has unilluminated corners that never go dark and
    ramp up to saturation over ~20 px. They are smaller than the background
    opening, so they would otherwise flatten into a bright rim of fake cells.
    """
    idx = np.linspace(0, len(paths) - 1, n_samples).astype(int)
    darkest = np.min([load_frame(source, paths[i]) for i in idx], axis=0)
    mask = (darkest < 0.6).astype(np.uint8)
    # Keep only the main illuminated field, then pull away from its edge.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    if n > 1:
        mask = (labels == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
    return cv2.erode(mask, kernel, borderType=cv2.BORDER_REPLICATE).astype(bool)
