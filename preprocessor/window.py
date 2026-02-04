'''
This script is used to preprocess the TIFF movie by extracting a window of the movie.
'''

import tifffile as tif
import numpy as np
import cv2
import os
import sys
import argparse

def extract_window(tiff_file, output_file, start_frame=10, end_frame=20, start_row=100, start_col=150, end_row=300, end_col=350):
    '''
    Extract a window of the TIFF movie using tifffile and numpy.
    '''
    stack = tif.imread(tiff_file) # Returns a numpy array (T, Y, X) or (T, C, Y, X)

    # Subset 1: Specific frames (temporal subset)
    frames_subset = stack[start_frame:end_frame, :, :]

    # Subset 2: Spatial window (spatial subset)
    spatial_subset = stack[:, start_row:end_row, start_col:end_col]

    # Subset 3: Combined
    combined_subset = stack[10:21, 100:300, 150:350]

    # Save the subset to a new file
    tif.imwrite(output_file, combined_subset)

def extract_window_memory_map(tiff_file, output_file, start_frame=10, end_frame=20, start_row=100, start_col=150, end_row=300, end_col=350):
    '''
    Extract a window of the TIFF movie using memory map.
    '''
    stack = tif.memmap(tiff_file) # Returns a numpy array (T, Y, X) or (T, C, Y, X)

    # Subset 1: Specific frames (temporal subset)
    frames_subset = stack[start_frame:end_frame, :, :]

    # Subset 2: Spatial window (spatial subset)
    spatial_subset = stack[:, start_row:end_row, start_col:end_col]

    # Subset 3: Combined
    combined_subset = stack[start_frame:end_frame, start_row:end_row, start_col:end_col]

    # Save the subset to a new file
    tif.imwrite(output_file, combined_subset)

def extract_window_2(tiff_file, output_file, start_frame=10, end_frame=20, start_row=100, start_col=150, end_row=300, end_col=350):
    '''
    Extract a window of the TIFF movie using cv2.
    '''
    ret, images = cv2.imreadmulti(tiff_file, flags=cv2.IMREAD_ANYCOLOR)

    if ret:
        # OpenCV convention: images[frame_idx][y:y+h, x:x+w]
        cropped_frames = [img[start_row:end_row, start_col:end_col] for img in images[start_frame:end_frame]]
        
        # Save the cropped frames to a new file
        cv2.imwrite(output_file, cropped_frames)
