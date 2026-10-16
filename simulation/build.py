"""
Build the per-frame Gaussian models for every source and export them for the
web viewer.

For each source (c1_inverted, timeconvol) this writes two models:
  image   Gaussians fitted to the frames themselves (simulation.gaussians.decompose)
  spots   Gaussians from the TrackMate spots tracked on that source (trial_4 / trial_5)

Outputs (simulation/output/, gitignored):
  <source>_<kind>.npz           one row per Gaussian, column arrays + "frame"
  web/<source>_<kind>/meta.json  viewer metadata
  web/<source>_<kind>/chunk_NNN.bin  CHUNK frames each, see write_web()

Example:
  python -m simulation.build                       # everything, all frames
  python -m simulation.build --sources timeconvol --kinds image --frames 0:400
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .frames import (
    FRAME_SIZE, N_FRAMES, PIXEL_TO_MICRON, REPO_ROOT, SECONDS_PER_FRAME, SOURCES,
    flatten, frame_paths, load_frame, valid_mask,
)
from .field import HEIGHT_MODELS, reference_amplitude
from .gaussians import FIELDS, DecomposeParams, decompose, load_spot_gaussians

OUTPUT_DIR = REPO_ROOT / "simulation" / "output"
CHUNK = 50
WEB_FIELDS = FIELDS  # x y sxx sxy syy area mass peak track, all float32

# Worker state, set once per process by _init_worker.
_W: dict = {}


def normalization_scale(source, paths, mask, n_samples: int = 32) -> float:
    """99.5th percentile of the flattened intensity over the movie: maps cells to ~[0, 1]."""
    idx = np.linspace(0, len(paths) - 1, n_samples).astype(int)
    sample = np.stack([flatten(load_frame(source, paths[i]), source.flatten_radius)[mask] for i in idx])
    return float(np.percentile(sample, 99.5))


def _init_worker(source_name: str, paths: list[Path], mask: np.ndarray, scale: float, params: DecomposeParams):
    _W.update(source=SOURCES[source_name], paths=paths, mask=mask, scale=scale, params=params)


def _decompose_frame(f: int) -> dict[str, np.ndarray]:
    src = _W["source"]
    flat = flatten(load_frame(src, _W["paths"][f]), src.flatten_radius) * _W["mask"] / _W["scale"]
    return decompose(flat, _W["params"])


def build_image_model(source_name: str, frames: range, params: DecomposeParams, workers: int) -> pd.DataFrame:
    src = SOURCES[source_name]
    paths = frame_paths(src.frames_dir)
    if len(paths) != N_FRAMES:
        print(f"warning: {src.frames_dir} has {len(paths)} frames, expected {N_FRAMES}")
    mask = valid_mask(src, paths)
    scale = normalization_scale(src, paths, mask)
    print(f"[{source_name}/image] scale={scale:.3f} valid={mask.mean():.3f} frames={len(frames)}")

    t0 = time.time()
    parts = []
    with ProcessPoolExecutor(workers, initializer=_init_worker,
                             initargs=(source_name, paths, mask, scale, params)) as pool:
        for k, (f, g) in enumerate(zip(frames, pool.map(_decompose_frame, frames, chunksize=8))):
            parts.append(pd.DataFrame({"frame": np.full(len(g["x"]), f), **g}))
            if (k + 1) % 500 == 0:
                print(f"  {k + 1}/{len(frames)} frames  {time.time() - t0:.0f}s")
    df = pd.concat(parts, ignore_index=True)
    print(f"[{source_name}/image] {len(df)} Gaussians in {time.time() - t0:.0f}s")
    return df


def build_spot_model(source_name: str, frames: range) -> pd.DataFrame:
    df = load_spot_gaussians(SOURCES[source_name])
    df = df[(df["frame"] >= frames.start) & (df["frame"] < frames.stop)].reset_index(drop=True)
    print(f"[{source_name}/spots] {len(df)} Gaussians from {SOURCES[source_name].spots_csv.name}")
    return df


def save_npz(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **{c: df[c].to_numpy() for c in df.columns})


def load_model(source_name: str, kind: str) -> pd.DataFrame:
    with np.load(OUTPUT_DIR / f"{source_name}_{kind}.npz") as z:
        return pd.DataFrame({k: z[k] for k in z.files})


def floor_pattern(viewer_dir: Path) -> dict:
    """File-name pattern of the viewer frames, e.g. ('..._C1_', 4, '.jpg')."""
    paths = frame_paths(viewer_dir) if viewer_dir.exists() else []
    if not paths:
        return {"floor_prefix": None, "floor_pad": 0, "floor_ext": ""}
    m = re.match(r"^(.*?)(\d+)(\.\w+)$", paths[0].name)
    prefix, pad, ext = m.group(1), len(m.group(2)), m.group(3)
    for i, p in enumerate(paths):
        if p.name != f"{prefix}{i:0{pad}d}{ext}":
            raise ValueError(f"{viewer_dir}: {p.name} breaks the frame naming pattern")
    return {"floor_prefix": prefix, "floor_pad": pad, "floor_ext": ext}


def write_web(df: pd.DataFrame, source_name: str, kind: str, n_frames: int) -> None:
    """
    Chunked little-endian binaries for the viewer. Chunk c covers frames
    [c*CHUNK, (c+1)*CHUNK) and holds:
      uint32 counts[CHUNK]
      float32 data[sum(counts) * len(WEB_FIELDS)]   row-major, WEB_FIELDS order
    """
    src = SOURCES[source_name]
    out = OUTPUT_DIR / "web" / f"{source_name}_{kind}"
    out.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(["frame"], kind="stable")
    counts = np.bincount(df["frame"].to_numpy(int), minlength=n_frames)[:n_frames]
    data = df[list(WEB_FIELDS)].to_numpy(np.float32)
    starts = np.concatenate([[0], np.cumsum(counts)])

    n_chunks = (n_frames + CHUNK - 1) // CHUNK
    for c in range(n_chunks):
        f0, f1 = c * CHUNK, min((c + 1) * CHUNK, n_frames)
        chunk_counts = np.zeros(CHUNK, np.uint32)
        chunk_counts[: f1 - f0] = counts[f0:f1]
        rows = data[starts[f0]:starts[f1]]
        with open(out / f"chunk_{c:03d}.bin", "wb") as fh:
            fh.write(chunk_counts.astype("<u4").tobytes())
            fh.write(rows.astype("<f4").tobytes())

    amp_ref = {model: reference_amplitude(df, model) for model in HEIGHT_MODELS}
    meta = {
        "source": source_name,
        "kind": kind,
        "n_frames": n_frames,
        "frame_size": FRAME_SIZE,
        "chunk": CHUNK,
        "n_chunks": n_chunks,
        "fields": list(WEB_FIELDS),
        "counts": counts.tolist(),
        "seconds_per_frame": SECONDS_PER_FRAME,
        "pixel_to_micron": PIXEL_TO_MICRON,
        # Floor texture: <repo root>/<floor_dir>/<prefix><zero-padded frame><ext>
        "floor_dir": os.path.relpath(src.viewer_dir, REPO_ROOT),
        **floor_pattern(src.viewer_dir),
        "amp_ref": amp_ref,
        "max_track": int(df["track"].max()) if len(df) else -1,
    }
    (out / "meta.json").write_text(json.dumps(meta))
    print(f"  web export -> {out.relative_to(REPO_ROOT)} ({n_chunks} chunks, {data.nbytes / 1e6:.1f} MB)")


def update_index() -> None:
    """simulation/output/web/index.json lists the exported models for the viewer."""
    web = OUTPUT_DIR / "web"
    models = sorted(p.name for p in web.iterdir() if (p / "meta.json").exists())
    (web / "index.json").write_text(json.dumps({"models": models}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Gaussian models + web export.")
    parser.add_argument("--sources", nargs="+", default=list(SOURCES), choices=list(SOURCES))
    parser.add_argument("--kinds", nargs="+", default=["image", "spots"], choices=["image", "spots"])
    parser.add_argument("--frames", default=f"0:{N_FRAMES}", help="start:stop frame range")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--no-web", action="store_true", help="Skip the web export.")
    parser.add_argument("--web-only", action="store_true",
                        help="Re-export the viewer data from existing .npz models without rebuilding.")
    args = parser.parse_args()

    start, stop = (int(v) for v in args.frames.split(":"))
    frames = range(start, stop)
    params = DecomposeParams()

    for source_name in args.sources:
        for kind in args.kinds:
            if args.web_only:
                write_web(load_model(source_name, kind), source_name, kind, stop)
                continue
            if kind == "image":
                df = build_image_model(source_name, frames, params, args.workers)
            else:
                df = build_spot_model(source_name, frames)
            save_npz(df, OUTPUT_DIR / f"{source_name}_{kind}.npz")
            if not args.no_web:
                write_web(df, source_name, kind, stop)
    if not args.no_web:
        update_index()


if __name__ == "__main__":
    main()
