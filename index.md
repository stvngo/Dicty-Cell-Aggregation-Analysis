---
layout: default
title: Dictyostelium Motility and Cell Aggregation Dynamics
description: Biophysics and Computer Vision Research Project - Cell Tracking and Velocity Analysis
---

# Dictyostelium Motility and Cell Aggregation Dynamics

**Biophysics and Computer Vision Research Project** under *Dr. Wouter-Jan Rappel* and *PhD Student Yi-Chieh Lai* at **UCSD Department of Physics**.

<p align="center">
  <img src="assets/img/cell_tracking_1.gif" alt="Cell tracking trajectories" height="260"/>
  <img src="assets/img/cosine_vs_time_surface_long.gif" alt="Cosine vs Time Surface" height="260"/>
</p>

## Introduction

*Dictyostelium discoideum* is a social amoeba that, upon starvation, initiates a collective aggregation process to survive. Individual cells chemotax toward waves of cAMP, forming complex streaming patterns, mounds, and eventually a migrating multicellular slug. This process, regulated by **cAMP** signaling and cell adhesion, leads to the formation of a fruiting body.

## Research Objectives

- Process TIFF file(s) from lab via thresholding.
- Each frame is 15 seconds.
- There are thousands of amoeba cells in movie, aggregating into 6 large cells by the end of the film.
- Use **ImageJ/Fiji's** built-in cell tracking algorithms (**TrackMate**) and libraries to model the position and velocity of a subset of these cells over time, particularly:
    - their movement *parallel/orthogonal to the Flamindo2 band*, and 
    - their movement *relative to each other/cluster centers*.

## Problems

The cells contain a fluorescent marker, called **Flamindo2**, which goes dark if the intracellular cAMP concentration is high. **Cyclic AMP (cAMP)** is the chemoattractant, in other words, the chemical the cells respond to under starvation. These waves of cyclic AMP sweep over the cells in a periodic fashion. Cells relay the chemoattractant signal: if they experience a high cyclic AMP concentration around their cell body, they begin to make cAMP and will secrete it, causing them to become **dark**.

The presence of this global wave/band of Flamindo2 moving from the top-right to the bottom-left of the (subset) of the Petri dish from the laboratory causes cells to move out of vision during thresholding, which poses a large challenge.

The **field of view is also much smaller** than the experimental Petri dish (cells may move out of frame), so **we do not know where these waves originate from**.

## Solutions

**1. Analyze a window/subset of the TIFF movie for a proof of concept**
- Even if it is for a few seconds, model the movement of the cells between the bands before the cells begin to disappear.
- Select a subset or a window of the TIFF movie;

<p align="center">
  <img src="assets/img/bottom_left_subset.png"
       alt="Example window chosen at frame 705 in bottom-right corner"
       title="Example window chosen at frame 705 in bottom-right corner"
       width="60%"/>
</p>

**2. Persist the tracking of cells during disappearance if they have not moved too far**
- Keep tracking the cells' location when they have disappeared, freezing the tracker's position of the cell before it disappears, and continue tracking after it reappears.

## Processing Pipeline

Using the C1 movie (without waves), we developed a preprocessing and tracking pipeline that produces improved tracking results by reducing noise and focusing on larger cell clusters.

The full process consists of five main steps:

1. **Pixel Inversion**: Invert the entire stack's pixels so cells appear light against a dark background, improving contrast for detection.

2. **Spatial and Temporal Windowing**: 
   - Select a spatial window from the stack
   - Filter frames to focus on aggregation periods (e.g., frames 1200-4000, where distinct clusters become clearer)

**ROI Geometry** (ImageJ units):

<p align="center">

| Axis | Min | Max | Step (Δ) |
|------|-----|-----|----------|
| **X** | 154 | 397 | 1.00000 |
| **Y** | 211 | 435 | 1.00000 |
| **Z** | 0   | 0   | 1.00000 |
| **T** | 0   | 2799| 1.00000 |

</p>

3. **Cell Detection via Thresholding**:
   - Use thresholding detector with simplified contours to detect each cell (intensity threshold: 17604)
   - Filter groups with radius >= 8.04 pixels to focus on larger clusters
   - This reduces tracking issues from small clusters that frequently disappear and reappear

4. **Advanced Kalman Tracker (AKT)**:
   - Hyperparameters tuned for merging/splitting events
   - Improved tracking stability: contours disappear less frequently, reducing "jumpy" tracks

5. **Track Analysis**: Generate tracking data including spots, tracks, edges, and branches (cell hierarchy) CSV files for further analysis.

## Data Analysis Methodology

### Tools and Libraries

Our analysis pipeline leverages modern Python data science tools:

- **Pandas**: Data loading, manipulation, and aggregation of TrackMate CSV files
- **NumPy**: Numerical operations, vector calculations, and array manipulation
- **Matplotlib & Seaborn**: Static 2D and 3D visualizations (histograms, scatter plots, heatmaps, surface plots)
- **Plotly**: Interactive 3D visualizations for exploratory data analysis
- **Scikit-learn**: Machine learning pipelines for classification and regression analysis

### Wave Velocity Analysis

#### Dot Product and Cosine Alignment

We computed the alignment between cell velocities and the cAMP wave direction using vector dot products:

- **Velocity Components**: Calculated `V_x` and `V_y` from spot positions and time, converting from pixels to micrometers and accounting for coordinate system transformations (ImageJ Y-down to standard math Y-up)
- **Wave Direction Vector**: Defined unit vector components `wave_x_unit = -0.875`, `wave_y_unit = -0.485` in standard mathematical coordinates
- **Cosine Alignment**: Computed `cosine = (V_x_unit · wave_x_unit) + (V_y_unit · wave_y_unit)` to measure how well each cell's velocity aligns with the wave direction
  - Values near +1: moving strongly with the wave
  - Values near -1: moving strongly against the wave
  - Values near 0: moving perpendicular to the wave

#### Parallel and Orthogonal Velocity Components

Decomposed cell velocities into components relative to the wave:

- **V_parallel**: Component of velocity along the wave direction (projection onto wave vector)
- **V_orthogonal**: Component of velocity perpendicular to the wave direction

This decomposition allows us to distinguish between cells moving toward/away from the wave origin versus those moving tangentially.

### Exploratory Data Analysis (EDA)

#### 2D Visualizations

- **Histograms**: Distribution of cosine values, showing strong bimodal peaks at ±1
- **Scatter Plots**: Cosine vs time, V_parallel vs V_orthogonal, velocity components over time
- **2D Histograms**: Time vs cosine distribution, revealing temporal patterns in alignment
- **Heatmaps**: Cosine alignment over time vs track ID, showing which tracks respond to waves and when

#### 3D Visualizations

- **3D Bimodal Distributions**: Cosine vs feature (EDGE_TIME, SPEED, V_parallel, etc.) vs frequency
  - Both bar chart and smooth surface plot variants
  - Interactive Plotly surfaces for rotation and zoom
- **3D Surface Plots**: Time vs cosine vs edge count, providing comprehensive views of alignment patterns

### Per-Track Mean-Velocity Cosine (Noise Reduction)

To reduce noise from frame-to-frame velocity fluctuations, we developed a **track-level aggregation** approach:

- **Mean Velocity Vector**: For each track, compute the mean `V_x` and `V_y` across all edges
- **Mean-Velocity Cosine**: Calculate the cosine of this mean velocity vector with the wave direction
- **Advantages**: 
  - Captures net migration direction rather than instantaneous fluctuations
  - More stable and interpretable than per-edge cosine averaging
  - Better suited for track-level classification and analysis

This approach revealed a **unimodal distribution** (compared to the bimodal per-edge distribution), suggesting that while individual edges show high variability, tracks have more consistent net alignment patterns.

### Longest Track Analysis

We identified and visualized the longest track in the dataset:

- **Trajectory Plot**: Spatial path of the cell over time
- **Position vs Time**: X and Y coordinates as functions of time
- **Velocity Components**: V_parallel and V_orthogonal over time
- **Cosine Alignment**: How alignment with wave changes over the track's lifetime
- **Speed Profile**: Magnitude of velocity over time

This detailed single-track analysis provides insights into individual cell behavior and serves as a validation of our tracking and analysis pipeline.

### Slug Centroid Methodology

To analyze cell dynamics relative to the aggregated slug, we developed a **centroid-based coordinate system**:

#### Coordinate Transformation

- **Centroid Position**: Identified slug centroid at `(270.08, 307.07)` in ImageJ coordinates
- **Relative Positions**: Computed `dx_centroid` and `dy_centroid` for each edge
- **Coordinate System Conversion**: Flipped Y-component to match math coordinates (consistent with velocity vectors)

#### Radial and Tangential Decomposition

- **Radial Unit Vector**: `r_hat = (dx, dy) / ||(dx, dy)||` pointing from centroid to cell
- **Tangential Unit Vector**: `t_hat = (-r_hat_y, r_hat_x)` (90° rotation)
- **Radial Velocity**: `v_radial = V · r_hat` (toward/away from centroid)
- **Tangential Velocity**: `v_tangential = V · t_hat` (around the centroid)

#### Radial Cosine Analysis

Similar to wave alignment, we computed **radial cosine**:

- **Radial Cosine**: Alignment of velocity unit vector with radial direction from centroid
  - Values near -1: moving strongly toward the centroid (aggregating)
  - Values near +1: moving strongly away from the centroid
  - Values near 0: mostly tangential motion (circling)

#### Centroid-Based EDA

- **2D Histograms**: Distance vs radial cosine, time vs radial cosine
- **3D Surfaces**: Time vs radial cosine vs frequency, distance vs radial cosine vs frequency
- **Spatial Trajectories**: Tracks colored by mean radial cosine, revealing convergence patterns

### Radial Acceleration Analysis

To investigate forces acting on cells, we computed **radial acceleration**:

#### Acceleration Calculation

- **Change in Radial Velocity**: `Δv_radial = v_radial(t) - v_radial(t-1)`
- **Time Step**: `Δt = EDGE_TIME(t) - EDGE_TIME(t-1)`
- **Radial Acceleration**: `a_radial = Δv_radial / Δt`

This metric reveals whether cells are accelerating toward or away from the slug centroid, potentially indicating attractive or repulsive forces.

#### Acceleration EDA

- **Scatter Plots**: Acceleration vs time, acceleration vs distance to centroid
- **2D Histograms**: Time vs acceleration distribution
- **3D Interactive Surfaces**: Time vs radial cosine vs mean acceleration
- **Binned Analysis**: Mean acceleration by distance bins to identify force-distance relationships

### Machine Learning Analysis

#### Classification Model

Using track-level features, we built a logistic regression classifier:

- **Features**: Mean EDGE_TIME, mean SPEED, track displacement
- **Target**: Binary classification (mean-velocity cosine < -0.7 = moving toward wave)
- **Pipeline**: StandardScaler → LogisticRegression with GridSearchCV
- **Results**: Achieved interpretable coefficients showing which features predict wave-aligned movement

#### Interactive Decision Surface

Created 3D interactive Plotly visualizations of the logistic regression decision surface, showing probability of wave alignment as a function of track features.

## Key Findings

1. **Bimodal Cosine Distribution**: Per-edge cosine values show strong peaks at ±1, indicating cells either strongly align with or against the wave direction, rather than random orientation.

2. **Temporal Patterns**: Early frames show more extreme cosine values (both positive and negative), while later frames show more variability, consistent with aggregation dynamics.

3. **Track-Level Stability**: Mean-velocity cosine per track shows a unimodal distribution, suggesting that while individual edges are noisy, tracks have consistent net migration directions.

4. **Centroid Convergence**: Radial cosine analysis reveals cells moving toward the slug centroid, with acceleration patterns suggesting distance-dependent forces.

5. **Spatial Clustering**: Tracks with low mean-velocity cosine (poor wave alignment) show distinct spatial patterns, potentially representing cells in different aggregation phases.

## Results and Outputs

Tracking results show promising signs of cell response to waves (e.g., a long purple track moving toward upper right), though further analysis is needed to confirm wave-velocity relationships.

**Output Data**: Tracking results (spots, tracks, edges, branches CSV files) are available in [`results/trial_3/`](results/trial_3).

**Video**: [Tracking visualization (frames 1200-4000 at 60 fps)](https://drive.google.com/file/d/163sUff1nipgEXZRfvcQ-P1H_oR9RZeLi/view?usp=sharing)

## Current Limitations

1. **Inconsistent Splitting/Merging Events**: When two distinct cells merge, a new cell ID is assigned. These merged cells can split immediately after, creating new contours and IDs.

2. **Frame Gap Parameter Trade-offs**: The max frame gap parameter requires careful tuning—too low causes disappearing tracks, too high risks incorrect linking.

3. **Temporal Tracking Patterns**: Early-middle frames show constant splitting/merging, while later frames become more stable as clusters fully aggregate.

4. **Limited Split/Merge Detection**: Analysis shows almost no successors or predecessors detected for most cells, suggesting split/merge events may not be properly captured.

## Next Steps

- Develop strategy for extracting cluster center positions from tracking data
- Implement wave velocity calculation methodology
- Improve split/merge event detection and tracking consistency
- Statistical testing of acceleration-distance relationships
- Comparative analysis of wave-aligned vs non-aligned tracks

## Reproducibility

> Note: although tracks can be fully reproduced with the above hyperparameters, the track colors and cell IDs will be different. The extracted data (e.g., position, time) should be the same.

Further analysis can be found at [`analysis/edge-features.ipynb`](analysis/edge-features.ipynb)
