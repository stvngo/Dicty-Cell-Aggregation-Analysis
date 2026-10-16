# 3D lift of the aggregation movie

Each 2D frame is turned into a set of **anisotropic Gaussians, one per cell or cell cluster**. The Gaussians are lifted into a third dimension. Overlapping Gaussians add, so when cells stream together their bumps form a ridge and then fuse into one taller mound.

## Pipeline

1. **Flatten** each frame (`frames.py`):
   - c1 is inverted on load; `preprocessor/invert.py` also writes `data/jpg/c1_inverted/`.
   - A coarse grey opening removes the illumination vignette.
   - The unlit corners of c1 are masked.
2. **Decompose** each frame (`gaussians.decompose`):
   - Seed regions at h-maxima, then run a watershed.
   - Merge neighbouring regions across shallow saddles (saddle ≥ 0.72 × the dimmer peak). Texture inside an aggregate collapses into one region, while the dark gap between two touching cells keeps them separate until they really fuse.
   - Each region becomes an intensity-weighted moment fit: centroid, covariance, area, mass and peak.
3. **TrackMate spots** (`gaussians.load_spot_gaussians`) give a second, independent model per source: c1 ↔ trial_4 and timeconvol ↔ trial_5. Their ellipse fits become covariances, `TRACK_ID` is kept for coloring, and trial_5's reversed time is undone.
4. **Lift** (`field.py`). The height model decides what *z* means:

   | model | height of Gaussian *i* | reads as |
   |---|---|---|
   | `mound` (default) | √(area/π) · peak | Each object is a dome as tall as its radius, so aggregates tower over single cells. |
   | `intensity` | peak | Brightness. |
   | `mass` | Σintensity / (2π√det Σ) | Volume under the Gaussian equals the summed intensity. |

   There are two ways to sum the Gaussians:
   - **Height field**: z = Σ Hᵢ gᵢ(x, y).
   - **3D density**: ρ = Σ exp(−½(dᵀΣᵢ⁻¹d + z²/σzᵢ²)). Its 1/e iso-surface makes each lone cell a dome of height Hᵢ, and nearby domes fuse like metaballs.

## Run

```bash
python -m simulation.build                      # ~13 min, all 4000 frames, both sources, image + spots models
python -m simulation.build --web-only           # re-export viewer data from the saved .npz models

# Interactive viewer: serve the REPO ROOT, then open the page
python -m http.server 8000
#   http://localhost:8000/simulation/viewer/
#   URL state works too: ?model=timeconvol_spots&mode=metaballs&color=track&frame=2400

# Offline MP4 (1920x1080, H.264, 2D frame inset), ~10-15 min each
python -m simulation.render --source timeconvol --mode surface
python -m simulation.render --source c1_inverted --mode metaballs --orbit 50
python -m simulation.render --source timeconvol --kind spots --frames 0:4000:4 --height mass
```

Outputs are written to `simulation/output/` (gitignored):

- `<source>_<kind>.npz`: one row per Gaussian
- `web/`: chunked float32 data for the viewer
- `renders/*.mp4`

## Viewer

There are three render modes over the same Gaussians:

- **Surface**: a height-field mesh. Low ground shows the microscopy frame, and raised Gaussians blend into a colormap. It has shadows from a key light placed at the top-right, the cAMP source side.
- **Metaballs**: a GPU ray-marched iso-surface of the 3D density.
- **Gaussian splats**: 3D Gaussian splatting. Each Gaussian is a 3D Gaussian on the floor, EWA-projected to the screen and alpha-blended back to front.

You can also:

- Color by height, by TrackMate track (spots models only) or by the image.
- Switch the height model, z exaggeration and σ scale live.
- Use the time slider and playback: Space plays or pauses, ←/→ steps one frame, and Shift+←/→ steps 50.
- Save a PNG of the current view.
