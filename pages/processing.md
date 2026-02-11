---
layout: default
title: Processing Pipeline
description: Preprocessing and tracking pipeline for cell detection and analysis
permalink: /processing/
background: /assets/img/pages/dicty.png
---

# Processing Pipeline

Using the C1 movie (without waves), we developed a preprocessing and tracking pipeline that produces improved tracking results by reducing noise and focusing on larger cell clusters.

The full process consists of five main steps:

## 1. Pixel Inversion

Invert the entire stack's pixels so cells appear light against a dark background, improving contrast for detection.

## 2. Spatial and Temporal Windowing

Select a spatial window from the stack and filter frames to focus on aggregation periods (e.g., frames 1200-4000, where distinct clusters become clearer).

**ROI Geometry** (ImageJ units):

| Axis | Min | Max | Step (Δ) |
|------|-----|-----|----------|
| **X** | 154 | 397 | 1.00000 |
| **Y** | 211 | 435 | 1.00000 |
| **Z** | 0   | 0   | 1.00000 |
| **T** | 0   | 2799| 1.00000 |

<p align="center">
  <img src="{{ '/assets/img/bottom_left_subset.png' | relative_url }}"
       alt="Example window chosen at frame 705 in bottom-right corner"
       title="Example window chosen at frame 705 in bottom-right corner"
       width="60%"/>
</p>

## 3. Cell Detection via Thresholding

- Use thresholding detector with simplified contours to detect each cell (intensity threshold: 17604)
- Filter groups with radius >= 8.04 pixels to focus on larger clusters
- This reduces tracking issues from small clusters that frequently disappear and reappear

<p align="center">
  <img src="{{ '/assets/img/trial_3_cell_ids.png' | relative_url }}"
       alt="Detected cell IDs"
       width="60%"/>
</p>

## 4. Advanced Kalman Tracker (AKT)

- Hyperparameters tuned for merging/splitting events
- Improved tracking stability: contours disappear less frequently, reducing "jumpy" tracks

<p align="center">
  <img src="{{ '/assets/img/trial_3_trackscheme.png' | relative_url }}"
       alt="Track scheme visualization"
       width="60%"/>
</p>

## 5. Track Analysis

Generate tracking data including spots, tracks, edges, and branches (cell hierarchy) CSV files for further analysis.

<p align="center">
  <img src="{{ '/assets/viz/trial_3/Plot_of_N_spots_vs_T.png' | relative_url }}"
       alt="Number of spots vs time"
       width="60%"/>
</p>
