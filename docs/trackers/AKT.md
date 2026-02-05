# Advanced Kalman Tracker

This tracker is an extended version of the Kalman tracker, that adds the possibility to customize linking costs and detect track fusion (segments merging) and track division (segments splitting).

This tracker is especially well suited to objects that move following a nearly constant velocity vector. The velocity vectors of each object can be completely different from one another. But for the velocity vector of one object need not to change too much from one frame to another.

In the frame-to-frame linking step, the classic Kalman tracker infer most likely spot positions in the target frame from growing tracks and link all extrapolated positions against all spots in the target frame, based on the square distance. This advanced version of the tracker allows for penalizing links to spots with different features values using the same framework that of the LAP tracker in TrackMate. Also, after the frame-to-frame linking step, track segments are post-processed to detect splitting and merging events, and perform gap-closing. This is again based on the LAP tracker implementation.