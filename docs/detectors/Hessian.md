# Hessian Detector

This detector is based on computing the determinant of the Hessian matrix of the image to detector bright blobs.

It can be configured with a different spots size in XY and Z. It can also return a normalized quality value, scaled from 0 to 1 for the spots of each time-point.

As discussed in *Mikolajczyk et al.* (2005), this detector has a better edge response elimination than the LoG detector and is suitable for detect spots in images with many strong edges.