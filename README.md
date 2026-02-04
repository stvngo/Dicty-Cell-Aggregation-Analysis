# Amoeba (Dicty) Motility and Cell Aggregation Under Starvation
Biophysics and Machine Learning Research Project under *Dr. Wouter-Jan Rappel* and *PhD Student Yi-Chieh Lai* at **UCSD Department of Physics**.

## Idea

- Process TIFF file(s) from lab via thresholding.
- Each frame is 15 seconds.
- There are over a thousand tiny amoeba cells in movie, aggregate into 6 large cells by the end of the film.
- Use **ImageJ/Fiji's** built-in cell tracking algorithms and libraries to model the position and velocity of a subset of these cells over time, particularly:
    - their movement *parallel/orthogonal to the Flamindo2 band*, and 
    - their movement *relative to each other*.


## Problems

The cells contain a fluorescent marker, called **Flamindo2**, which goes dark if the intracellular cAMP concentration is high. **Cyclic AMP (cAMP)** is the chemoattractant, in other words, the chemical the cells respond to under starvation. These waves of cyclic AMP sweep over the cells in a periodic fashion. Cells relay the chemoattractant signal: if they experience a high cyclic AMP concentration around their cell body, they begin to make cAMP and will secrete it, causing them to become **dark**.

The presence of this global wave/band of Flamindo2 moving from the top-right to the bottom-left of the (subset) of the Petri dish from the laboratory causes cells to move out of vision during thresholding, which poses a large challenge.

The **field of view is also much smaller** than the experimental Petri dish (cells may move out of frame), so **we do not know where these waves originate from**.

## Solutions

Proposed by Dr. Rappel, we have the following solutions:

**1. Analyze a window/subset of the TIFF movie for a proof of concept**
- Even if it is for a few seconds, model the movement of the cells between the bands before the cells begin to disappear.
- Select a subset or a window of the TIFF movie;

![Image cannot load.](assets/img/bottom_left_subset.png "Example window chosen at frame 705 in bottom-right corner")

**2. Persist the tracking of cells during disappearance if they have not moved too far**
- Keep tracking the cells' location when they have disappeared, freezing the tracker's position of the cell before it disappears, and continue tracking after it reappears.

## Particle/Cell Tracking Algorithms

A variety of tracking algorithms are available under ImageJ/Fiji. We are most interested in those that can detect and handle **merging events**, since our Dicty cells aggregate over time. We use the following algorithms to capture smaller cells merging into a larger cell.

Many of these algorithms include hyperparameters (i.e., radius, persistence, thresholds, pixels), that must be tuned to accurately capture frame-by-frame movement of cells.

Other available methods have been used, e.g., using contour detection via Python (cv2); however, there has been no success so far. There remain algorithms yet to have been attempted, such as YOLOby Ultralytics, which may provide tracking and plotting trajectories, but may need additional data preprocessing (format conversion, 16-bit support, performance optimization via 8-bit PNG frames).

## Run

### preprocessor/window.py 
```bash
python -m preprocessor.window \
  --input path/to/movie.tif \
  --output path/to/window.tif \
  --start-frame 10 --end-frame 20 \
  --start-row 100 --end-row 300 \
  --start-col 150 --end-col 350
```

or force full load into RAM:
```bash
python -m preprocessor.window --input in.tif --output out.tif --no-memmap
```