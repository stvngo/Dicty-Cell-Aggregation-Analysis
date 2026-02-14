# Next Steps - Meeting Notes

**Date**: [Date of meeting]  
**Attendees**: [Your name], PhD Student

## Overview

Following discussion with the PhD student, we have identified several new research directions to enhance our understanding of cell aggregation dynamics and local cAMP signaling effects.

---

## 1. Mean Squared Displacement (MSD) Analysis

### Objective
Analyze how far cells move from their starting positions over time to distinguish between random diffusion and directed migration.

### Implementation
- Compute MSD for each track: `MSD(t) = ⟨|r(t) - r(0)|²⟩`
- Plot MSD vs time to identify diffusion regimes:
  - **Normal diffusion**: MSD ∝ t (linear)
  - **Directed motion**: MSD ∝ t² (quadratic)
  - **Subdiffusion**: MSD ∝ t^α where α < 1
  - **Superdiffusion**: MSD ∝ t^α where α > 1
- Compare MSD patterns across different time windows and cell clusters

### Expected Insights
- Determine if cells exhibit random walk behavior or directed migration toward aggregation sites
- Identify temporal phases of motion (early random → later directed)

---

## 2. Local Density Effects Analysis

### Problem Statement
Current tree-like merging analysis doesn't capture **high-density regional effects**. We need to understand if high-density regions attract nearby cells.

### Research Questions
- Given a high-density cell, do other cells move towards it?
- How does local cell density affect the velocities of neighboring cells?
- Is there a distance-dependent attraction effect?

### Methodology
- Define "high-density regions" (e.g., cells with N neighbors within radius R)
- For each high-density cell, compute velocities of nearby cells toward it
- Compare attraction patterns for high-density vs low-density regions
- Spatial analysis: distance from high-density region vs velocity magnitude/direction

---

## 3. Local cAMP Signaling Hypothesis

### Background
- **cAMP source**: Far off in top-right corner (not visible in frame)
- **Cell behavior**: Cells secrete cAMP (chemoattractant), creating wave patterns
- **Initial state**: Sparse cells create global-looking wave because cAMP spreads widely
- **Later state**: As cells cluster, some large cells may **stop secreting cAMP**

### Hypothesis
When a cell stops secreting cAMP (loses signaling), other cells should move **less** toward it, indicating that cAMP concentration affects cell-to-cell attraction.

### Validation Strategy
1. **Cross-reference with cAMP signal data**:
   - Use video data showing cAMP signal intensity (darkness = cAMP concentration)
   - Identify when cAMP signal stops for a given cell
   - Measure velocities of other cells toward that cell before/after signal loss

2. **Quantitative Analysis**:
   - Compare cell attraction strength when cAMP signal is present vs absent
   - Test correlation: cAMP intensity (darkness) vs velocity of other cells toward source
   - Temporal analysis: track signal loss events and corresponding velocity changes

### Expected Findings
- Cells with active cAMP signaling should attract other cells more strongly
- Loss of cAMP signaling should reduce attraction
- This would validate that local cAMP concentration drives cell aggregation

---

## 4. Time-Binned Velocity Analysis

### Objective
Improve temporal resolution by analyzing velocity patterns within smaller time windows.

### Methodology
- **Bin time into intervals**: 300-500 frames per bin
- **Compute average velocities** within each time bin
- **Track changes** in velocity patterns across bins
- Compare with global (per-track) averages to identify temporal dynamics

### Benefits
- Fine-grained analysis of "when" velocity changes occur
- Identify temporal phases of aggregation
- Detect transitions in cell behavior (e.g., when cAMP signaling changes)

### Implementation Notes
- Choose bin size based on frame rate and expected signal duration
- Overlap bins if needed for smoother transitions
- Aggregate by track, spatial region, or density class

---

## 5. Acceleration Analysis - Not Recommended

### Decision
**Do not pursue acceleration analysis** at this time.

### Rationale
- Velocity data is already noisy
- Taking derivatives (acceleration = d(velocity)/dt) amplifies noise
- Acceleration values would not be informative for current research questions
- Focus on velocity patterns and MSD instead

---

## Implementation Priority

1. **High Priority**:
   - MSD analysis (foundational metric)
   - Time-binned velocity analysis (improves temporal resolution)

2. **Medium Priority**:
   - Local density effects analysis (requires spatial density calculations)

3. **Future Work** (requires additional data):
   - Local cAMP signaling validation (needs cAMP signal intensity data from video)

---

## Technical Notes

### MSD Calculation
```python
# For each track:
# 1. Get initial position r(0)
# 2. For each time point t, compute |r(t) - r(0)|²
# 3. Average over all tracks (or analyze per-track)
```

### Time Binning
```python
# Example: 300-frame bins
bin_size = 300
for bin_start in range(0, max_frame, bin_size):
    bin_end = bin_start + bin_size
    # Compute average velocities in this bin
```

### Density Calculation
```python
# For each cell at each time point:
# 1. Count neighbors within radius R
# 2. Classify as high/low density
# 3. Compute velocities of nearby cells toward this cell
```

---

## Questions for Follow-up

- What is the frame rate of the video? (needed for time binning)
- Do we have access to cAMP signal intensity data (darkness measurements)?
- What radius should be used to define "high-density" regions?
- Should we analyze all tracks or focus on specific subsets (e.g., longest tracks)?

---

## References

- **MSD in Statistical Mechanics**: Mean Squared Displacement is a key metric for characterizing diffusion and transport processes
- **RMSD**: Root Mean Squared Displacement = √MSD (gives displacement in same units as position)
