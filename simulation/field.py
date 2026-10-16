"""
Turn a frame's Gaussians into 3D: a height field z = H(x, y) or a 3D density
rho(x, y, z) whose iso-surface gives metaball-like blobs.

Height models (what the third dimension means), per Gaussian i:

  mound      H_i = sqrt(area_i / pi) * peak_i
             A cell or aggregate is a dome as tall as its equivalent radius,
             so merging clusters grow into taller mounds (Dicty aggregates are
             3D mounds). Default.
  intensity  H_i = gain * peak_i
             Brightness as height; every object has the same scale.
  mass       H_i = gain * mass_i / (2 pi sqrt(det S_i))
             Volume under the Gaussian equals the region's summed intensity.

Overlapping Gaussians add, so neighbours that approach each other raise a
ridge between them and fuse into one peak once the saddle disappears.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit, prange

HEIGHT_MODELS = ("mound", "intensity", "mass")


def amplitudes(g: pd.DataFrame | dict, model: str = "mound", gain: float = 1.0) -> np.ndarray:
    """Per-Gaussian height H_i. Mirrored by rawAmplitude() in viewer/viewer.js."""
    area = np.asarray(g["area"], float)
    peak = np.clip(np.asarray(g["peak"], float), 0.0, 1.5)
    if model == "mound":
        return np.sqrt(area / np.pi) * peak
    if model == "intensity":
        return gain * peak
    if model == "mass":
        det = np.asarray(g["sxx"]) * np.asarray(g["syy"]) - np.asarray(g["sxy"]) ** 2
        return gain * np.asarray(g["mass"], float) / (2 * np.pi * np.sqrt(np.clip(det, 1.0, None)))
    raise ValueError(f"Unknown height model {model!r}; choose from {HEIGHT_MODELS}")


def reference_amplitude(g: pd.DataFrame | dict, model: str) -> float:
    """
    Height that maps to the top of the scene / colormap for a whole movie.

    99.9th percentile rather than the max: early TrackMate blobs that span the
    dense carpet (trial_4) would otherwise flatten everything else.
    """
    amp = amplitudes(g, model)
    return float(np.percentile(amp, 99.9)) if amp.size else 1.0


def _params(g, sigma_scale: float):
    s2 = sigma_scale**2
    return (
        np.ascontiguousarray(g["x"], dtype=np.float64),
        np.ascontiguousarray(g["y"], dtype=np.float64),
        np.ascontiguousarray(np.asarray(g["sxx"], float) * s2),
        np.ascontiguousarray(np.asarray(g["sxy"], float) * s2),
        np.ascontiguousarray(np.asarray(g["syy"], float) * s2),
    )


@njit(cache=True)
def _splat2d(out, x, y, sxx, sxy, syy, amp, px_per_cell, cutoff):
    ny, nx = out.shape
    for i in range(x.size):
        det = sxx[i] * syy[i] - sxy[i] * sxy[i]
        if det <= 1e-9 or amp[i] <= 0:
            continue
        ia, ib, ic = syy[i] / det, -sxy[i] / det, sxx[i] / det
        rx = cutoff * np.sqrt(sxx[i]) / px_per_cell
        ry = cutoff * np.sqrt(syy[i]) / px_per_cell
        cx = x[i] / px_per_cell - 0.5
        cy = y[i] / px_per_cell - 0.5
        x0, x1 = max(0, int(cx - rx)), min(nx - 1, int(cx + rx) + 1)
        y0, y1 = max(0, int(cy - ry)), min(ny - 1, int(cy + ry) + 1)
        for r in range(y0, y1 + 1):
            dy = (r + 0.5) * px_per_cell - y[i]
            for c in range(x0, x1 + 1):
                dx = (c + 0.5) * px_per_cell - x[i]
                q = ia * dx * dx + 2 * ib * dx * dy + ic * dy * dy
                if q < cutoff * cutoff:
                    out[r, c] += amp[i] * np.exp(-0.5 * q)


@njit(cache=True, parallel=True)
def _splat3d(out, x, y, sxx, sxy, syy, sz, px_per_cell, dz, cutoff):
    # Parallel over z-slices so no two threads write the same voxel.
    nz, ny, nx = out.shape
    for k in prange(nz):
        z = k * dz
        for i in range(x.size):
            if sz[i] <= 0:
                continue
            qz = (z / sz[i]) ** 2
            if qz >= cutoff * cutoff:
                continue
            det = sxx[i] * syy[i] - sxy[i] * sxy[i]
            if det <= 1e-9:
                continue
            ia, ib, ic = syy[i] / det, -sxy[i] / det, sxx[i] / det
            lim = cutoff * cutoff - qz
            scale = np.sqrt(lim) / px_per_cell
            rx = scale * np.sqrt(sxx[i])
            ry = scale * np.sqrt(syy[i])
            cx = x[i] / px_per_cell - 0.5
            cy = y[i] / px_per_cell - 0.5
            x0, x1 = max(0, int(cx - rx)), min(nx - 1, int(cx + rx) + 1)
            y0, y1 = max(0, int(cy - ry)), min(ny - 1, int(cy + ry) + 1)
            for r in range(y0, y1 + 1):
                dy = (r + 0.5) * px_per_cell - y[i]
                for c in range(x0, x1 + 1):
                    dx = (c + 0.5) * px_per_cell - x[i]
                    q = ia * dx * dx + 2 * ib * dx * dy + ic * dy * dy
                    if q < lim:
                        out[k, r, c] += np.exp(-0.5 * (q + qz))


def height_field(
    g, shape: int = 256, frame_size: int = 512, model: str = "mound",
    sigma_scale: float = 1.0, cutoff: float = 3.5,
) -> np.ndarray:
    """z = sum_i H_i * exp(-1/2 d^T S_i^-1 d) on a shape x shape grid (z in px)."""
    out = np.zeros((shape, shape), np.float64)
    if len(g["x"]) == 0:
        return out
    x, y, sxx, sxy, syy = _params(g, sigma_scale)
    amp = np.ascontiguousarray(amplitudes(g, model), dtype=np.float64)
    _splat2d(out, x, y, sxx, sxy, syy, amp, frame_size / shape, cutoff)
    return out


def density_volume(
    g, shape: int = 192, nz: int = 48, z_max: float = 48.0, frame_size: int = 512,
    model: str = "mound", sigma_scale: float = 1.25, z_scale: float = 1.0,
    cutoff: float = 3.0,
) -> tuple[np.ndarray, float]:
    """
    rho(x, y, z) = sum_i exp(-1/2 (d^T S_i^-1 d + z^2 / sz_i^2)), z >= 0.

    With sz_i = z_scale * H_i / sqrt(2), the iso-surface rho = 1/e of a lone
    Gaussian is a dome of height z_scale * H_i over an ellipse of sqrt(2)
    standard deviations, and overlapping domes fuse like metaballs.
    Returns (volume[nz, shape, shape], dz in px).
    """
    out = np.zeros((nz, shape, shape), np.float32)
    dz = z_max / (nz - 1)
    if len(g["x"]) == 0:
        return out, dz
    x, y, sxx, sxy, syy = _params(g, sigma_scale)
    sz = np.ascontiguousarray(z_scale * amplitudes(g, model) / np.sqrt(2), dtype=np.float64)
    _splat3d(out, x, y, sxx, sxy, syy, sz, frame_size / shape, dz, cutoff)
    return out, dz


ISO_LEVEL = float(np.exp(-1.0))
