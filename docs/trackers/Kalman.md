# Kalman Tracker

This tracker is best suited for objects that move with a roughly constant velocity vector.

It relies on the Kalman filter to predict the next most likely position of a spot. The predictions for all current tracks are linked to the spots actually found in the next frame, thanks to the LAP framework already present in the LAP tracker. Predictions are continuously refined and the tracker can accommodate moderate velocity direction and magnitude changes.
This tracker can bridge gaps: If a spot is not found close enough to a prediction, then the Kalman filter will make another prediction in the next frame and re-iterate the search.
The first frames of a track are critical for this tracker to work properly: Tracksare initiated by looking for close neighbors (again via the LAP tracker). Spurious spots in the beginning of each track can confuse the tracker.

This tracker needs two parameters (on top of the maximal frame gap tolerated): - the max search radius defines how far from a predicted position it should look for candidate spots; - the initial search radius defines how far two spots can be apart when initiating a new track. 

Documentation online: https://imagej.net/plugins/trackmate/trackers/kalman-tracker