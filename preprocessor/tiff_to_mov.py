'''
Convert a TIFF movie to a MOV movie.
'''

import cv2
import numpy as np
import tifffile as tif

def tiff_to_mov(tiff_file, mov_file):
    '''
    Convert a TIFF movie to a MOV movie.
    '''
    tiff_file = cv2.imread(tiff_file)
    cv2.imwrite(mov_file, tiff_file)

if __name__ == "__main__":
    tiff_to_mov("movie.tif", "movie.mov")