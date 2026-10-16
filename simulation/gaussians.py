"""
Per-frame Gaussian decomposition of the movie: one anisotropic 2D Gaussian per
cell / cell cluster, from either the image itself or TrackMate spots.

A frame's Gaussians are stored as a dict of equal-length arrays (pixel units,
image coordinates: x right, y down):

  x, y            intensity-weighted centroid
  sxx, sxy, syy   intensity-weighted covariance (px^2)
  area            region area (px^2)
  mass            summed flattened intensity (normalized units * px^2)
  peak            max smoothed intensity in the region (normalized, ~[0, 1])
  track           TrackMate TRACK_ID, -1 for image-derived Gaussians

The height model (what the third dimension means) is applied later from these
features, see ``simulation.field.amplitudes``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage.morphology import h_maxima
from skimage.segmentation import watershed

from .frames import N_FRAMES, PIXEL_TO_MICRON, Source

FIELDS = ("x", "y", "sxx", "sxy", "syy", "area", "mass", "peak", "track")


@dataclass(frozen=True)
class DecomposeParams:
    smooth_sigma: float = 1.0   # px; pre-smoothing before seeding/watershed
    threshold: float = 0.16     # normalized intensity that counts as cell
    h: float = 0.04             # absolute prominence a peak needs to seed a region
    merge_ratio: float = 0.72   # merge neighbours whose saddle >= ratio * dimmer peak
    min_area: int = 6           # px^2; smaller regions are noise


def merge_shallow_saddles(labels: np.ndarray, smooth: np.ndarray, ratio: float) -> np.ndarray:
    """
    Fuse adjacent watershed regions separated by a shallow saddle.

    The test is relative (saddle >= ratio * the dimmer of the two peaks), so it
    behaves the same for dim single cells and saturated aggregates: texture
    inside an aggregate merges away, while the dark gap between two touching
    cells keeps them apart until they really fuse.
    """
    n = int(labels.max())
    if n < 2:
        return labels
    peaks = np.zeros(n + 1)
    peaks[1:] = ndi.maximum(smooth, labels, index=np.arange(1, n + 1))

    # Every 4-connected pixel pair that straddles two regions; the pass level
    # across that pair is the dimmer of its two pixels.
    a = np.concatenate([labels[:, :-1].ravel(), labels[:-1, :].ravel()])
    b = np.concatenate([labels[:, 1:].ravel(), labels[1:, :].ravel()])
    s = np.concatenate([
        np.minimum(smooth[:, :-1], smooth[:, 1:]).ravel(),
        np.minimum(smooth[:-1, :], smooth[1:, :]).ravel(),
    ])
    sel = (a != b) & (a > 0) & (b > 0)
    lo, hi, s = np.minimum(a[sel], b[sel]), np.maximum(a[sel], b[sel]), s[sel]
    keys, inv = np.unique(lo.astype(np.int64) * (n + 1) + hi, return_inverse=True)
    saddle = np.full(keys.size, -np.inf)
    np.maximum.at(saddle, inv, s)
    pa, pb = keys // (n + 1), keys % (n + 1)

    # Union-find, highest saddles first (a persistence-style merge tree).
    parent = np.arange(n + 1)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for j in np.argsort(-saddle):
        ra, rb = find(pa[j]), find(pb[j])
        if ra != rb and saddle[j] >= ratio * min(peaks[ra], peaks[rb]):
            parent[rb] = ra
            peaks[ra] = max(peaks[ra], peaks[rb])

    lut = np.array([find(i) for i in range(n + 1)])
    _, relabeled = np.unique(lut, return_inverse=True)
    return relabeled[labels]


def decompose(flat: np.ndarray, params: DecomposeParams = DecomposeParams()) -> dict[str, np.ndarray]:
    """
    Split a flattened, normalized frame into cell regions and moment-fit a
    Gaussian to each.

    Seeds are h-maxima of the smoothed image; the watershed regions are then
    fused across shallow saddles. Touching cells therefore keep separate
    Gaussians until the dip between them fills in, at which point they merge
    into one wider Gaussian: the aggregation event we want to see in 3D.
    """
    smooth = ndi.gaussian_filter(flat, params.smooth_sigma)
    fg = smooth > params.threshold
    seeds = h_maxima(smooth, params.h).astype(bool) & fg
    markers, _ = ndi.label(seeds)
    labels = watershed(-smooth, markers, mask=fg)
    labels = merge_shallow_saddles(labels, smooth, params.merge_ratio)

    n = int(labels.max())
    if n == 0:
        return empty()

    lab = labels.ravel()
    w = np.clip(flat, 0.0, None).ravel()
    h_img, w_img = flat.shape
    yy, xx = np.divmod(np.arange(lab.size), w_img)

    def sums(values: np.ndarray) -> np.ndarray:
        return np.bincount(lab, weights=values, minlength=n + 1)[1:]

    area = np.bincount(lab, minlength=n + 1)[1:].astype(np.float64)
    m0 = sums(w)
    keep = (area >= params.min_area) & (m0 > 0)
    m0 = np.where(m0 > 0, m0, 1.0)

    mx = sums(w * xx) / m0
    my = sums(w * yy) / m0
    # Central second moments; +1/12 is the variance of a single pixel.
    sxx = sums(w * xx * xx) / m0 - mx**2 + 1 / 12
    syy = sums(w * yy * yy) / m0 - my**2 + 1 / 12
    sxy = sums(w * xx * yy) / m0 - mx * my
    peak = ndi.maximum(smooth, labels, index=np.arange(1, n + 1))

    out = {
        "x": mx, "y": my, "sxx": sxx, "sxy": sxy, "syy": syy,
        "area": area, "mass": m0, "peak": np.asarray(peak),
        "track": np.full(n, -1),
    }
    return {k: v[keep] for k, v in out.items()}


def empty() -> dict[str, np.ndarray]:
    return {k: np.zeros(0) for k in FIELDS}


def load_spot_gaussians(source: Source) -> pd.DataFrame:
    """
    TrackMate spots as Gaussians, in pixel units and forward time.

    Shape comes from TrackMate's fitted ellipse (semi-axes a >= b, angle theta).
    A uniform ellipse has second moments a^2/4 and b^2/4 along its axes, which
    makes these directly comparable to the image moment fits.
    """
    cols = ["TRACK_ID", "POSITION_X", "POSITION_Y", "FRAME", "AREA",
            "MEAN_INTENSITY_CH1", "MAX_INTENSITY_CH1", "TOTAL_INTENSITY_CH1",
            "ELLIPSE_MAJOR", "ELLIPSE_MINOR", "ELLIPSE_THETA"]
    df = pd.read_csv(source.spots_csv, header=0, skiprows=[1, 2, 3], usecols=cols)

    to_px = 1 / PIXEL_TO_MICRON if source.spots_in_microns else 1.0
    frame = df["FRAME"].to_numpy(int)
    if source.spots_time_reversed:
        frame = (N_FRAMES - 1) - frame

    a = df["ELLIPSE_MAJOR"].to_numpy(float) * to_px
    b = df["ELLIPSE_MINOR"].to_numpy(float) * to_px
    theta = df["ELLIPSE_THETA"].to_numpy(float)
    # Degenerate ellipse fits fall back to the equal-area circle.
    area = df["AREA"].to_numpy(float) * to_px**2
    bad = ~np.isfinite(a) | ~np.isfinite(b) | (a <= 0) | (b <= 0)
    r_eq = np.sqrt(area / np.pi)
    a = np.where(bad, r_eq, a)
    b = np.where(bad, r_eq, b)
    theta = np.where(np.isfinite(theta), theta, 0.0)

    c, s = np.cos(theta), np.sin(theta)
    va, vb = a**2 / 4, b**2 / 4
    out = pd.DataFrame({
        "frame": frame,
        "x": df["POSITION_X"].to_numpy(float) * to_px,
        "y": df["POSITION_Y"].to_numpy(float) * to_px,
        "sxx": va * c**2 + vb * s**2,
        "sxy": (va - vb) * c * s,
        "syy": va * s**2 + vb * c**2,
        "area": area,
        "mass": df["TOTAL_INTENSITY_CH1"].to_numpy(float) / 255.0,
        "peak": df["MAX_INTENSITY_CH1"].to_numpy(float) / 255.0,
        "track": df["TRACK_ID"].to_numpy(int),
    })
    return out.sort_values(["frame", "track"]).reset_index(drop=True)
