# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Biophysics and computer vision research at UCSD Physics (Rappel lab; mentor Yi-Chieh Lai). The subject is starving *Dictyostelium discoideum* amoebae chemotaxing toward cAMP and aggregating into clusters. All current work uses **one movie**: "Capture 4 - Position 1". It has 4000 frames at 512×512 px, **15 s per frame**, and **3.731309 µm per pixel**. Cells drift and aggregate toward the **top-right** (food/cAMP source). cAMP waves travel **top-right → bottom-left** as dark bands. The Flamindo2 reporter goes dark when intracellular cAMP is high.

**Documentation layout.**

- `README.md` is current as of Oct 2026 and covers motivation, data, results, wave detection, open problems and setup.
- `docs/processing_pipeline.md` holds the imaging problem, TrackMate parameters per trial and the trial_3 findings.
- `readme_old.md` is the archived trial_3-era README.
- **`pages/` (the Jekyll GitHub Pages site) is still out of date**, describing trial_3 as of Feb 2026.

The README embeds `assets/video/*.mp4`, which is un-ignored in `.gitignore`, and figures exported from the edge-features-3 notebook in `assets/img/trial_5/`.

## Data channels (same movie, different renderings)

| Folder (`data/jpg/…`, `data/png/…`) | What it is | Used for |
|---|---|---|
| `c0` | Fluorescence: dark background, bright cells, **with the dark cAMP wave**. Under thresholding, cells disappear and reappear as a wave passes | Wave detection |
| `waves` | A differently normalized export of c0, named `…_C0NNNN.jpg` | Roboflow inference input |
| `c1` | Same movie with a white background, dark cells and **no wave**. Inverted in ImageJ before tracking; a pre-inverted copy is in `data/jpg/c1_inverted` | trial_4 |
| `highdensity_timeconvol` | c0 convolved over time. Removes the wave and tracks far more stably | trial_5 (best) |

`data/raw/*.tif` (2 GB+), `data/jpg/`, `data/png/`, `*.tif`, `*.mp4` and `roboflow/images/results/` are gitignored.

## Pipeline

1. **TIFF → frames**: `preprocessor/tiff_to_png_jpg.py` writes `data/{png,jpg}/<c0|c1|stem>/`.
2. **Detection and tracking in Fiji/TrackMate**, not Python: thresholding detector → **Advanced Kalman Tracker** (see `docs/trackers/AKT.md`) → export spots/edges/tracks CSVs to `results/trial_N/`. Parameters are logged in `docs/experiments/*.md`. trial_5 used threshold 99, initial and Kalman search radius 5, and max frame gap 30.
3. **Analysis in notebooks**:
   - `analysis/edge-features-2.ipynb` analyzes trial_4 (c1).
   - `analysis/edge-features-3.ipynb` analyzes trial_5 (timeconvol). This is the newest analysis and a superset of the earlier one.
   - `edge-features.ipynb` (trial_3) and trials 1–3 are historical.
   - Ignore `field-embedding.ipynb`, `image-pca.ipynb`, `extra.ipynb`, `edge-features-2.ipynb.broken`, and the CSVs those notebooks wrote (`results/trial_5/field_features_per_time.csv`, `image_pca_scores.csv`).

## Analysis conventions (read before touching notebook code)

- **Notebooks are 8–13 MB** because of embedded outputs. Don't Read them whole. Pull out cell sources with a short `json` script, and use NotebookEdit for changes.
- Notebook cell 0 calls `os.chdir` to the repo root, so every path is repo-root-relative. The notebooks import helpers via `from utils import …` (`analysis/utils.py`: `save_gif` writes to `assets/img/`, `plot_3d_distribution`, `plot_interactive_3d_surface`).
- **TrackMate CSVs carry 4 header rows**: `pd.read_csv(path, header=0, skiprows=[1, 2, 3])`.
- **trial_5 was tracked on a time-reversed stack.** Cell 1 of edge-features-3 un-reverses `POSITION_T`, `FRAME`, `EDGE_TIME`, `TRACK_START`/`TRACK_STOP` and **swaps `SPOT_SOURCE_ID` ↔ `SPOT_TARGET_ID`**. Any new code that loads trial_5 CSVs must do the same. trial_4 is not reversed.
- `edges` is merged with `spots` twice (source and target) to build `merged`, which has `POSITION_{X,Y,T}_{source,target}`.
- **Velocity** is currently per edge (consecutive spots, Δt ≈ 1 frame). It is converted to µm/s with the constants above, and **V_y is negated** (ImageJ is y-down; the analysis uses math y-up). Every image-coordinate vector gets the same flip, e.g. the centroid displacement `dy`.
- **Wave direction** is the fixed unit vector `(-0.875, -0.485)` in math coordinates, pointing down-left. `cosine = v̂ · ŵ`. **cosine ≈ −1 means moving against the wave, toward the top-right source**: this is the chemotactic signal and the chemotaxis index (CI) proxy. The "−1 peaks" discussed in the notebooks refer to this.
- The final-aggregate centroid is the position of the target spot on the latest edge, about (270, 309) in image coordinates. It drives the radial/tangential velocity and radial-acceleration sections.

## Wave detection (`roboflow/`)

- **Model**: a single-class ("Waves") instance-segmentation model with polygon masks. It was fine-tuned on Roboflow (dataset `dicty-waves-zfpmy` v3, RF-DETR/YOLO) from roughly 100–200 hand-labeled frames, including null frames, with SAM3-assisted labeling. Validation accuracy is in the mid-to-high 90s. `roboflow/notebooks/rf_detr_wave_detection.ipynb` is a Colab training template that still contains tutorial leftovers.
- **`roboflow/images/workflow.py`** runs the Roboflow serverless workflow on every frame in `data/jpg/waves`. For each frame it writes an annotated `.jpg` and a `.json` to `roboflow/images/results/<date>/`. It needs `.env` (copy `.env.template`) and is resumable.
- **`results/2026-05-16_232640/` is the complete run**: all 4000 frames, plus `tracked_*.mp4`, `wave_velocity.csv/png` and `stack.tif`. `results/2026-05-16/` is an earlier partial run.
- **JSON schema**: `blob["predictions"]["predictions"]` is a list of `{x, y, width, height, confidence, class, points:[{x,y},…]}`. The parsing and geometry helpers are in `roboflow/images/wave_geometry.py`. Its `frame_index_from_name` regex `_C(\d+)` matches the `waves` naming (`_C00500`) but mis-parses c0 naming (`_C0_0500`).
- `tracker.py` runs either `--offline` (ByteTrack via `supervision` on the saved JSON) or `--stream` (the Roboflow video-stream API). `wave_velocity_plot.py` tracks the centroid of the largest polygon in each frame, which is fragile for the reasons below.
- **Known behavior and failure modes**:
  - Waves start around **frame 260**.
  - Detection is good until about **frame 1100–1250**, then degrades: as clusters form, the dark gaps between them look like waves.
  - 1–4 waves can be visible at once.
  - Some frames drop a detection, or part of a wave.
  - Wave direction rotates over the movie, from a top-down slant to mostly right-to-left (still slanted), and speed changes too.
  - Because of the dropped detections, a per-frame velocity/area analysis over frames 260–1100 hasn't worked yet.

## 3D lift (`simulation/`)

This is a side project, separate from the analysis. It turns each frame into per-cell anisotropic Gaussians and lifts them into 3D as a height field, a metaball density or 3D Gaussian splats. Pipeline, commands and height models are in `simulation/README.md`. Things that need more than one file to see:

- **Source pairing.** `frames.SOURCES` pairs each image source with its TrackMate run: `c1_inverted` ↔ trial_4 (µm, forward time) and `timeconvol` ↔ trial_5 (px, time-reversed).
- **Height model kept in two places.** It lives in `field.amplitudes` and is mirrored in `viewer/viewer.js:rawAmplitude`. Keep them in sync. Heights are normalized by `field.reference_amplitude` (p99.9), which `build.write_web` stores in `meta.json` as `amp_ref`.
- **Different world axes.** The viewer uses Three.js Y-up (image y → world Z). The PyVista renderer uses Z-up (image y → −world y). The image top sits on the far side in both.
- **PyVista gotchas.** Off-screen `Plotter.screenshot()` returns the last rendered image, so call `render()` first (`Renderer.shoot`). `smooth_shading=True` renders a filtered copy that ignores in-place point updates.
- **Generated data.** `simulation/output/` is gitignored, about 170 MB of viewer data.

## Open research threads (mentor meeting, 2026-05-27)

- **Make wave detection hold up past frame ~1250** by preprocessing frames and training on the preprocessed versions:
  - smooth the signal spatially (convolution over x/y);
  - define a per-pixel **phase** of the system, e.g. via a **Hilbert transform** of each pixel's detrended intensity time series, so wavefronts become phase isolines.
  - The user will also label late frames (zero waves, large separated clusters) as negatives.
- **Low-density movie(s) are coming.** The pipeline should generalize beyond this one high-density movie.
- **The early double cosine-peak puzzle** (the 3D time × cosine × frequency plots in edge-features-2/3): a −1 peak appears at the very start, and another around frame ~900. The ~900 peak is expected, since cells visibly speed toward the top-right then. The early one is suspicious. Mentor suggestions:
  - compute velocity over **Δt = 3–5 frames** instead of per edge;
  - bin time coarser during preprocessing;
  - query the edges/spots that have high CI near t = 0;
  - check whether the peak is a binning/scatter-resolution artifact or a real chemotactic effect;
  - condition on wave timing (a conditional probability using the wave detections).
  - The diagnostics so far are in edge-features-3's "Post-hoc analyses" section, starting at about cell 117: early-time cosine, bin-size sweep, stationary-edge share, quality vs time.
  - The surface mode of `analysis/utils.py:plot_3d_distribution` plotted `H.T` on an `indexing='ij'` mesh, which swapped cosine and time. This was fixed 2026-10-15. Saved notebook outputs made with `plot_type='surface'` before that date (e.g. edge-features-3 cell 39) are wrong until re-run. Bar charts and 2D histograms were never affected.
- Earlier threads are in `docs/meetings/next_steps.md`: MSD (done), time-binned velocity, local-density attraction, local cAMP signaling. Acceleration is deliberately not pursued because it amplifies noise.

## Commands

There are no tests, linter or build step. Use the project venv (Python 3.12):

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
jupyter notebook                                   # notebooks expect to run from repo root or analysis/

python preprocessor/tiff_to_png_jpg.py --raw-dir data/raw --output-dir data
python preprocessor/invert.py --input-dir data/png/c1 --output-dir data/jpg/c1_inverted
python -m preprocessor.window --input in.tif --output out.tif --start-frame 10 --end-frame 20 \
  --start-row 100 --end-row 300 --start-col 150 --end-col 350   # crop; drops ImageJ calibration metadata
python preprocessor/jpgs_to_mp4.py  --input-dir <frames_dir> --output <out.mp4>
python preprocessor/jpgs_to_tiff.py --input-dir <frames_dir> --output <out.tif>

python roboflow/images/workflow.py [--fresh | --no-resume | --output-dir DIR]   # calls the paid Roboflow API
python roboflow/images/tracker.py --offline --results-dir roboflow/images/results/2026-05-16_232640 \
  --waves-dir data/jpg/waves --output roboflow/images/results/2026-05-16_232640/tracked_60fps.mp4
python roboflow/images/wave_velocity_plot.py --results-dir roboflow/images/results/2026-05-16_232640
```

Other folders: `trackmate/` holds reference Java TrackMate edge-feature analyzers. `ultralytics-trackers/` and `yolo26n.pt` are an unused early YOLO tracking stub. `main.py` and `preprocessor/reverse.py` are empty.
