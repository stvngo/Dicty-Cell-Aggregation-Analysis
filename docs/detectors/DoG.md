# Differences of Gaussian (DoG) Detector

This detector is based on an approximation of the LoG operator by differences of Gaussian (DoG). Computations are made in direct space. It is the quickest for small spot sizes ( ~5 pixels).

Spots found too close are suppressed. This detector can do sub-pixel localization of spots using a quadratic fitting scheme. It is based on the scale-space framework made by Stephan Preibisch for ImgLib.

Documentation online: https://imagej.net/plugins/trackmate/detectors/difference-of-gaussian