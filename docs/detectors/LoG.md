# Laplacian of Gaussian (LoG) Detector

This detector applies a LoG (Laplacian of Gaussian) filter to the image, with a sigma suited to the blob estimated size. Calculations are made in the Fourier space. The maxima in the filtered image are searched for, and maxima too close from each other are suppressed. A quadratic fitting scheme allows to do sub-pixel localization.