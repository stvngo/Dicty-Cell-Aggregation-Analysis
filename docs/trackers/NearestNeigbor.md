# Nearest Neigbor Tracker

This tracker is the most simple one, and is based on nearest neighbor search.

For each pair of consecutive frames t1 and t2, it iterates through all spots in frame t1. For each source spot in t1, it searches for the nearest target spot in frame t2. If it is not already connected to a spot in frame t1, and is within the maximal linking distance, a link between the two spots is created.

The nearest neighbor search relies upon the KD-tree technique implemented in imglib2. This ensure a very efficient tracking and makes this tracker suitable for situation where a huge number of particles are to be tracked over a very large number of frames. However, because of the naiveness of its principles, it can result in pathological tracks. It can only do frame-to-frame linking; there cannot be any track merging or splitting, and gaps will not be closed. Also, the end results are non-deterministic, as the links created depend in the order in which the source spots are iterated.

Documentation online: https://imagej.net/plugins/trackmate/trackers/nearest-neighbor-tracke