# Linear Assignment Problem (LAP) Tracker

This tracker is based on the Linear Assignment Problem mathematical framework. Its implementation is adapted from the following paper: Robust single-particle tracking in live-cell time-lapse sequences - Jaqaman et al., 2008, Nature Methods.

Tracking happens in 2 steps: First spots are linked from frame to frame to build track segments. These track segments are investigated in a second step for gap-closing (missing detection), splitting and merging events.

Linking costs are proportional to the square distance between source and target spots, which makes this tracker suitable for Brownian motion. Penalties can be set to favor linking between spots that have similar features.

Solving the LAP relies on the Jonker-Volgenant solver, and a sparse cost matrix formulation, allowing it to handle very large problems.

Documentation online: https://imagej.net/plugins/trackmate/trackers/lap-trackers