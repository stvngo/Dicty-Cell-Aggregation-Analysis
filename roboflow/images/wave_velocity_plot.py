"""
Plot wave centroid velocity over time from per-frame Roboflow JSON.

Uses the largest polygon per frame (by contour area). Velocity is in px/s
using frame-index gaps and --seconds-per-frame (default 15 s per index step).

Example:
  python roboflow/images/wave_velocity_plot.py \\
    --results-dir roboflow/images/results/2026-05-16_232640
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_IMAGES_DIR = Path(__file__).resolve().parent
if str(_IMAGES_DIR) not in sys.path:
    sys.path.insert(0, str(_IMAGES_DIR))

from wave_geometry import frame_index_from_name, largest_polygon_centroid, parse_predictions_blob


def load_centroid_series(results_dir: Path, max_frames: int | None = None) -> pd.DataFrame:
    json_paths = sorted(
        (
            p
            for p in results_dir.glob("*.json")
            if "_C" in p.name and "trajectories" not in p.name.lower()
        ),
        key=lambda p: frame_index_from_name(p.name),
    )
    if max_frames is not None:
        json_paths = json_paths[:max_frames]

    rows: list[dict] = []
    for jp in json_paths:
        idx = frame_index_from_name(jp.name)
        blob = json.loads(jp.read_text(encoding="utf-8"))
        preds = parse_predictions_blob(blob)
        hit = largest_polygon_centroid(preds)
        if hit is None:
            rows.append(
                {"frame_idx": idx, "cx": np.nan, "cy": np.nan, "area_px": np.nan}
            )
        else:
            cx, cy, area = hit
            rows.append({"frame_idx": idx, "cx": cx, "cy": cy, "area_px": area})

    return pd.DataFrame(rows).sort_values("frame_idx").reset_index(drop=True)


def add_velocities(df: pd.DataFrame, seconds_per_frame: float) -> pd.DataFrame:
    out = df.copy()
    t = out["frame_idx"].astype(float).to_numpy()
    cx = out["cx"].to_numpy(dtype=float)
    cy = out["cy"].to_numpy(dtype=float)

    dt = np.diff(t)
    dt[dt <= 0] = np.nan
    dt_sec = dt * seconds_per_frame

    vx = np.full(len(out), np.nan)
    vy = np.full(len(out), np.nan)
    vx[1:] = np.diff(cx) / dt_sec
    vy[1:] = np.diff(cy) / dt_sec

    out["time_s"] = (t - t[0]) * seconds_per_frame
    out["vx_px_s"] = vx
    out["vy_px_s"] = vy
    out["speed_px_s"] = np.hypot(vx, vy)
    return add_direction(out, min_speed=0.0)


def add_direction(df: pd.DataFrame, min_speed: float) -> pd.DataFrame:
    """Unit direction and angle (deg); NaN where speed < min_speed."""
    out = df.copy()
    vx = out["vx_px_s"].to_numpy(dtype=float)
    vy = out["vy_px_s"].to_numpy(dtype=float)
    spd = out["speed_px_s"].to_numpy(dtype=float)
    mask = np.isfinite(spd) & (spd >= min_speed)

    ang = np.full(len(out), np.nan)
    ang[mask] = np.degrees(np.arctan2(vy[mask], vx[mask]))
    out["dir_deg"] = ang

    unwrapped = np.full(len(out), np.nan)
    valid_idx = np.where(mask)[0]
    if len(valid_idx) > 1:
        unwrapped[valid_idx] = np.degrees(np.unwrap(np.radians(ang[valid_idx])))
    out["dir_deg_unwrapped"] = unwrapped

    out["dir_ux"] = np.where(mask, vx / spd, np.nan)
    out["dir_uy"] = np.where(mask, vy / spd, np.nan)
    return out


def plot_velocities(df: pd.DataFrame, output_path: Path | None) -> None:
    valid = df.dropna(subset=["cx", "cy"])
    if valid.empty:
        raise SystemExit("No polygon centroids found in JSON results.")

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)

    axes[0].plot(valid["time_s"], valid["cx"], color="#2563eb", lw=0.8, label="cx")
    axes[0].plot(valid["time_s"], valid["cy"], color="#dc2626", lw=0.8, label="cy")
    axes[0].set_ylabel("Centroid (px)")
    axes[0].legend(loc="upper right")
    axes[0].set_title("Largest wave polygon — centroid position")

    vel = df.dropna(subset=["speed_px_s"])
    axes[1].plot(vel["time_s"], vel["vx_px_s"], color="#2563eb", lw=0.7, label="vx")
    axes[1].plot(vel["time_s"], vel["vy_px_s"], color="#dc2626", lw=0.7, label="vy")
    axes[1].axhline(0, color="gray", lw=0.5)
    axes[1].set_ylabel("Velocity (px/s)")
    axes[1].legend(loc="upper right")
    axes[1].set_title("Centroid velocity (forward difference)")

    axes[2].plot(vel["time_s"], vel["speed_px_s"], color="#059669", lw=0.8)
    axes[2].set_ylabel("|v| (px/s)")
    axes[2].set_xlabel("Time (s)")
    axes[2].set_title("Speed magnitude")

    fig.tight_layout()
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150)
        print(f"Saved {output_path}")
    plt.show()


def plot_velocity_direction(
    df: pd.DataFrame,
    output_path: Path | None,
    min_speed: float,
) -> None:
    vel = df[np.isfinite(df["dir_deg"])].copy()
    if vel.empty:
        raise SystemExit(
            f"No velocity directions with |v| >= {min_speed} px/s. Lower --min-speed."
        )

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    sc = axes[0].scatter(
        vel["time_s"],
        vel["dir_deg"],
        c=vel["speed_px_s"],
        s=6,
        cmap="viridis",
        alpha=0.65,
        linewidths=0,
    )
    axes[0].axhline(0, color="gray", lw=0.5)
    axes[0].axhline(90, color="gray", lw=0.3, ls="--")
    axes[0].axhline(-90, color="gray", lw=0.3, ls="--")
    axes[0].set_ylim(-180, 180)
    axes[0].set_ylabel("Direction (deg)")
    axes[0].set_title(
        f"Velocity direction (|v| ≥ {min_speed:g} px/s) — 0° = +x, 90° = +y (image down)"
    )
    cbar = fig.colorbar(sc, ax=axes[0], pad=0.01, fraction=0.02)
    cbar.set_label("|v| (px/s)")

    axes[1].plot(
        vel["time_s"],
        vel["dir_deg_unwrapped"],
        color="#7c3aed",
        lw=0.7,
        alpha=0.85,
    )
    axes[1].set_ylabel("Direction unwrapped (deg)")
    axes[1].set_title("Unwrapped heading (continuous rotation)")

    axes[2].plot(vel["time_s"], vel["dir_ux"], color="#2563eb", lw=0.7, label="ûx")
    axes[2].plot(vel["time_s"], vel["dir_uy"], color="#dc2626", lw=0.7, label="ûy")
    axes[2].axhline(0, color="gray", lw=0.5)
    axes[2].set_ylim(-1.05, 1.05)
    axes[2].set_ylabel("Unit direction")
    axes[2].set_xlabel("Time (s)")
    axes[2].legend(loc="upper right")
    axes[2].set_title("Normalized velocity components")

    fig.tight_layout()
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150)
        print(f"Saved {output_path}")
    plt.show()


def main() -> int:
    parser = argparse.ArgumentParser(description="Plot largest-wave centroid velocity over time.")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=_IMAGES_DIR / "results" / "2026-05-16_232640",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="PNG path (default: <results-dir>/wave_velocity.png)",
    )
    parser.add_argument(
        "--seconds-per-frame",
        type=float,
        default=15.0,
        help="Assay seconds between consecutive frame indices (default 15).",
    )
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV export path.")
    parser.add_argument(
        "--plot",
        choices=("speed", "direction", "both"),
        default="both",
        help="Which figures to generate (default: both).",
    )
    parser.add_argument(
        "--direction-output",
        type=Path,
        default=None,
        help="PNG for direction plot (default: <results-dir>/wave_velocity_direction.png).",
    )
    parser.add_argument(
        "--min-speed",
        type=float,
        default=0.5,
        help="Hide direction when |v| below this (px/s); reduces noise (default 0.5).",
    )
    args = parser.parse_args()

    results_dir = args.results_dir.resolve()
    if not results_dir.is_dir():
        raise SystemExit(f"Not a directory: {results_dir}")

    df = load_centroid_series(results_dir, max_frames=args.max_frames)
    df = add_velocities(df, args.seconds_per_frame)
    df = add_direction(df, min_speed=args.min_speed)

    n_valid = df["cx"].notna().sum()
    n_dir = df["dir_deg"].notna().sum()
    print(f"Frames: {len(df)} | with largest polygon: {n_valid} | direction samples: {n_dir}")
    if n_valid > 1:
        spd = df["speed_px_s"].dropna()
        print(f"Speed px/s — median: {spd.median():.2f}, max: {spd.max():.2f}")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.csv, index=False)
        print(f"Saved {args.csv}")

    if args.plot in ("speed", "both"):
        out = args.output or (results_dir / "wave_velocity.png")
        plot_velocities(df, out)

    if args.plot in ("direction", "both"):
        dir_out = args.direction_output or (results_dir / "wave_velocity_direction.png")
        plot_velocity_direction(df, dir_out, args.min_speed)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
