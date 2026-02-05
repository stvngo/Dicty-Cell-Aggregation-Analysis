# Label Image Detector

This detector creates spots by importing regions from a label image.

A label image is an image where the pixel values are integers. Each object in a label image is represented by a single common pixel value (the label) that is unique to the object.

This detector reads such an image and create spots from each object. In 2D the contour of a label is imported. In 3D, spherical spots of the same volume that the label are created.

The spot quality stores the object area or volume in pixels.

Documentation online: https://imagej.net/plugins/trackmate/detectors/trackmate-label-image-detector