---
layout: default
title: Results and Findings
permalink: /results/
---

# Results and Findings

## Key Findings

1. **Bimodal Cosine Distribution**: Per-edge cosine values show strong peaks at ±1, indicating cells either strongly align with or against the wave direction, rather than random orientation.

2. **Temporal Patterns**: Early frames show more extreme cosine values (both positive and negative), while later frames show more variability, consistent with aggregation dynamics.

3. **Track-Level Stability**: Mean-velocity cosine per track shows a unimodal distribution, suggesting that while individual edges are noisy, tracks have more consistent net migration directions.

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
