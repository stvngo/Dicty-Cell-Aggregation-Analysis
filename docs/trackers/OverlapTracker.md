# Overlap Tracker

This tracker is a simple extension of the Intersection - over - Union (IoU) tracker.

It generates links between spots whose shapes overlap between consecutive frames. When several spots are eligible as a source for a target, the one with the largest IoU is chosen.

The minimal IoU parameter sets a threshold below which links won't be created. The scale factor allows for enlarging (>1) or shrinking (<1) the spot shapes before computing their IoU. Two methods can be used to compute IoU: The  Fast  one approximates the spot shapes by their rectangular bounding-box. The  Precise  one uses the actual spot polygon.

This tracker works in 2D and 3D. However in 3D, the IoU is computed from the bounding-boxes regardless of the choice of the IoU computation method. The  Precise  method is not implemented.

Documentation online: https://imagej.net/plugins/trackmate/trackers/overlap-tracker