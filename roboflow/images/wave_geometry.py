"""Helpers for Roboflow wave polygon predictions."""

from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np


def frame_index_from_name(name: str) -> int:
    m = re.search(r"_C(\d+)", name, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def sorted_wave_frames(waves_dir: Path) -> list[Path]:
    paths = [
        p
        for p in waves_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    return sorted(paths, key=lambda p: frame_index_from_name(p.name))


def parse_predictions_blob(blob: dict) -> list[dict]:
    """Extract prediction dicts from workflow JSON or stream payload."""
    if not blob:
        return []
    preds = blob.get("predictions")
    if isinstance(preds, dict):
        items = list(preds.get("predictions") or [])
    elif isinstance(preds, list):
        items = preds
    else:
        items = []
    return [p for p in items if is_wave_segmentation(p)]


def is_wave_segmentation(pred: dict) -> bool:
    """
    True for Roboflow instance-seg detections (polygon or bbox).

    Stream trajectory_data points often have x/y only — exclude those.
    """
    if not isinstance(pred, dict):
        return False
    points = pred.get("points") or []
    if isinstance(points, list) and len(points) >= 3:
        return True
    has_xy = "x" in pred and "y" in pred
    has_size = ("width" in pred and "height" in pred) or ("w" in pred and "h" in pred)
    return has_xy and has_size


def points_to_contour(points: list[dict]) -> np.ndarray:
    pts = np.array([[float(p["x"]), float(p["y"])] for p in points], dtype=np.float32)
    return pts.reshape(-1, 1, 2)


def polygon_metrics(points: list[dict]) -> tuple[float, float, float, float]:
    """Return area_px, perimeter_px, centroid_x, centroid_y."""
    if len(points) < 3:
        return 0.0, 0.0, float("nan"), float("nan")
    contour = points_to_contour(points)
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, closed=True))
    moments = cv2.moments(contour)
    if moments["m00"] > 0:
        cx = moments["m10"] / moments["m00"]
        cy = moments["m01"] / moments["m00"]
    else:
        cx = float(np.mean(contour[:, 0, 0]))
        cy = float(np.mean(contour[:, 0, 1]))
    return area, perimeter, cx, cy


def largest_polygon_centroid(preds: list[dict]) -> tuple[float, float, float] | None:
    """Centroid (cx, cy) and area of the largest polygon among predictions."""
    best_area = -1.0
    best: tuple[float, float, float] | None = None
    for pred in preds:
        points = pred.get("points") or []
        if not isinstance(points, list) or len(points) < 3:
            continue
        area, _, cx, cy = polygon_metrics(points)
        if area > best_area:
            best_area = area
            best = (cx, cy, area)
    return best


def prediction_to_xyxy(pred: dict) -> np.ndarray:
    """BBox xyxy from polygon points or Roboflow center+width/height fields."""
    points = pred.get("points") or []
    if isinstance(points, list) and len(points) >= 3:
        contour = points_to_contour(points).astype(np.int32)
        x, y, w, h = cv2.boundingRect(contour)
        return np.array([x, y, x + w, y + h], dtype=np.float32)

    w = float(pred.get("width", pred.get("w", 0)))
    h = float(pred.get("height", pred.get("h", 0)))
    x = float(pred["x"])
    y = float(pred["y"])
    return np.array([x - w / 2, y - h / 2, x + w / 2, y + h / 2], dtype=np.float32)
