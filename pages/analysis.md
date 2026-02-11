---
layout: default
title: Data Analysis Methodology
description: Wave velocity analysis, centroid methodology, and exploratory data analysis
permalink: /analysis/
---

# Data Analysis Methodology

## Tools and Libraries

Our analysis pipeline leverages modern Python data science tools:

- **Pandas**: Data loading, manipulation, and aggregation of TrackMate CSV files
- **NumPy**: Numerical operations, vector calculations, and array manipulation
- **Matplotlib & Seaborn**: Static 2D and 3D visualizations (histograms, scatter plots, heatmaps, surface plots)
- **Plotly**: Interactive 3D visualizations for exploratory data analysis

## Wave Velocity Analysis

### Dot Product and Cosine Alignment

We computed the alignment between cell velocities and the cAMP wave direction using vector dot products:

- **Velocity Components**: Calculated `V_x` and `V_y` from spot positions and time, converting from pixels to micrometers and accounting for coordinate system transformations (ImageJ Y-down to standard math Y-up)
- **Wave Direction Vector**: Defined unit vector components `wave_x_unit = -0.875`, `wave_y_unit = -0.485` in standard mathematical coordinates
- **Cosine Alignment**: Computed `cosine = (V_x_unit · wave_x_unit) + (V_y_unit · wave_y_unit)` to measure how well each cell's velocity aligns with the wave direction
  - Values near +1: moving strongly with the wave
  - Values near -1: moving strongly against the wave
  - Values near 0: moving perpendicular to the wave

### Parallel and Orthogonal Velocity Components

Decomposed cell velocities into components relative to the wave:

- **V_parallel**: Component of velocity along the wave direction (projection onto wave vector)
- **V_orthogonal**: Component of velocity perpendicular to the wave direction

This decomposition allows us to distinguish between cells moving toward/away from the wave origin versus those moving tangentially.

## Exploratory Data Analysis (EDA)

### 2D Visualizations

- **Histograms**: Distribution of cosine values, showing strong bimodal peaks at ±1
- **Scatter Plots**: Cosine vs time, V_parallel vs V_orthogonal, velocity components over time
- **2D Histograms**: Time vs cosine distribution, revealing temporal patterns in alignment
- **Heatmaps**: Cosine alignment over time vs track ID, showing which tracks respond to waves and when

### 3D Visualizations

- **3D Bimodal Distributions**: Cosine vs feature (EDGE_TIME, SPEED, V_parallel, etc.) vs frequency
  - Both bar chart and smooth surface plot variants
  - Interactive Plotly surfaces for rotation and zoom
- **3D Surface Plots**: Time vs cosine vs edge count, providing comprehensive views of alignment patterns

## Per-Track Mean-Velocity Cosine (Noise Reduction)

To reduce noise from frame-to-frame velocity fluctuations, we developed a **track-level aggregation** approach:

- **Mean Velocity Vector**: For each track, compute the mean `V_x` and `V_y` across all edges
- **Mean-Velocity Cosine**: Calculate the cosine of this mean velocity vector with the wave direction
- **Advantages**: 
  - Captures net migration direction rather than instantaneous fluctuations
  - More stable and interpretable than per-edge cosine averaging
  - Better suited for track-level classification and analysis

This approach revealed a **unimodal distribution** (compared to the bimodal per-edge distribution), suggesting that while individual edges show high variability, tracks have more consistent net alignment patterns.

## Longest Track Analysis

We identified and visualized the longest track in the dataset:

- **Trajectory Plot**: Spatial path of the cell over time
- **Position vs Time**: X and Y coordinates as functions of time
- **Velocity Components**: V_parallel and V_orthogonal over time
- **Cosine Alignment**: How alignment with wave changes over the track's lifetime
- **Speed Profile**: Magnitude of velocity over time

<p align="center">
  <img src="{{ '/assets/img/trial_3_zoomed.png' | relative_url }}"
       alt="Longest track zoomed view"
       width="60%"/>
</p>

This detailed single-track analysis provides insights into individual cell behavior and serves as a validation of our tracking and analysis pipeline.

## Slug Centroid Methodology

To analyze cell dynamics relative to the aggregated slug, we developed a **centroid-based coordinate system**:

### Coordinate Transformation

- **Centroid Position**: Identified slug centroid at `(270.08, 307.07)` in ImageJ coordinates
- **Relative Positions**: Computed `dx_centroid` and `dy_centroid` for each edge
- **Coordinate System Conversion**: Flipped Y-component to match math coordinates (consistent with velocity vectors)

### Radial and Tangential Decomposition

- **Radial Unit Vector**: `r_hat = (dx, dy) / ||(dx, dy)||` pointing from centroid to cell
- **Tangential Unit Vector**: `t_hat = (-r_hat_y, r_hat_x)` (90° rotation)
- **Radial Velocity**: `v_radial = V · r_hat` (toward/away from centroid)
- **Tangential Velocity**: `v_tangential = V · t_hat` (around the centroid)

### Radial Cosine Analysis

Similar to wave alignment, we computed **radial cosine**:

- **Radial Cosine**: Alignment of velocity unit vector with radial direction from centroid
  - Values near -1: moving strongly toward the centroid (aggregating)
  - Values near +1: moving strongly away from the centroid
  - Values near 0: mostly tangential motion (circling)

### Centroid-Based EDA

- **2D Histograms**: Distance vs radial cosine, time vs radial cosine
- **3D Surfaces**: Time vs radial cosine vs frequency, distance vs radial cosine vs frequency
- **Spatial Trajectories**: Tracks colored by mean radial cosine, revealing convergence patterns

<p align="center">
  <img src="{{ '/assets/img/distance_to_centroid_vs_time.png' | relative_url }}"
       alt="Distance to centroid vs time"
       width="60%"/>
</p>

## Radial Acceleration Analysis

To investigate forces acting on cells, we computed **radial acceleration**:

### Acceleration Calculation

- **Change in Radial Velocity**: `Δv_radial = v_radial(t) - v_radial(t-1)`
- **Time Step**: `Δt = EDGE_TIME(t) - EDGE_TIME(t-1)`
- **Radial Acceleration**: `a_radial = Δv_radial / Δt`

This metric reveals whether cells are accelerating toward or away from the slug centroid, potentially indicating attractive or repulsive forces.

### Acceleration EDA

- **Scatter Plots**: Acceleration vs time, acceleration vs distance to centroid
- **2D Histograms**: Time vs acceleration distribution
- **3D Interactive Surfaces**: Time vs radial cosine vs mean acceleration
- **Binned Analysis**: Mean acceleration by distance bins to identify force-distance relationships

<p align="center">
  <img src="{{ '/assets/img/time_vs_radial_cosine_vs_mean_radial_accel.png' | relative_url }}"
       alt="Time vs radial cosine vs mean radial acceleration"
       width="60%"/>
</p>

<p align="center">
  <img src="{{ '/assets/img/mean_time_vs_mean-velocity_cosine_vs_track_count.png' | relative_url }}"
       alt="Mean time vs mean-velocity cosine vs track count"
       width="60%"/>
</p>
