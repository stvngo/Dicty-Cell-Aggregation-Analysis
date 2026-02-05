# Thresholding Detector

This detector creates spots by thresholding a grayscale image.

Pixels in the designated channel that have a value larger than the threshold are considered as part of the foreground, and used to build connected regions. In 2D, spots are created with the (possibly simplified) contour of the region. In 3D, a spherical spot is created for each region in its center, with a volume equal to the region volume.

The spot quality stores the object area or volume in pixels.

Documentation online: https://imagej.net/plugins/trackmate/detectors/trackmate-thresholding-detector