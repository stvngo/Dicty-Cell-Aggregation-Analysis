from collections import defaultdict
from pathlib import Path
import argparse

import cv2
import numpy as np
import tifffile as tif

from ultralytics import YOLO


def track_tiff(
    tiff_path: str | Path,
    model_path: str = "yolo26n.pt",
    show_display: bool = True,
) -> dict:
    """
    Track cells in a TIFF stack using YOLO.
    
    Returns:
        Dictionary with track_history
    """
    # Load the YOLO model
    model = YOLO(model_path)
    
    # Load the TIFF stack
    tiff_path = Path(tiff_path)
    stack = tif.imread(tiff_path)
    print(f"Loaded TIFF: shape={stack.shape}, dtype={stack.dtype}")

    # Handle different stack shapes and normalize if needed
    if stack.ndim == 3:
        # (T, Y, X) - grayscale
        n_frames, height, width = stack.shape
        is_grayscale = True
    elif stack.ndim == 4:
        # (T, C, Y, X) or (T, Y, X, C)
        if stack.shape[1] in (1, 3, 4):
            # (T, C, Y, X)
            n_frames, n_channels, height, width = stack.shape
            is_grayscale = n_channels == 1
        else:
            # (T, Y, X, C)
            n_frames, height, width, n_channels = stack.shape
            is_grayscale = n_channels == 1
    else:
        raise ValueError(f"Expected 3D or 4D stack, got shape={stack.shape}")

    # Normalize 16-bit to 8-bit if needed (YOLO expects uint8)
    if stack.dtype == np.uint16:
        print("Normalizing 16-bit to 8-bit...")
        stack = (stack / 256).astype(np.uint8)
    elif stack.dtype != np.uint8:
        # Convert other dtypes to uint8
        stack_min = stack.min()
        stack_max = stack.max()
        if stack_max > stack_min:
            stack = ((stack - stack_min) / (stack_max - stack_min) * 255).astype(np.uint8)
        else:
            stack = np.zeros_like(stack, dtype=np.uint8)

    # Store the track history
    track_history = defaultdict(lambda: [])

    # Loop through the TIFF frames
    for frame_idx in range(n_frames):
        # Extract frame from stack
        if stack.ndim == 3:
            frame = stack[frame_idx]  # (Y, X)
        elif stack.shape[1] in (1, 3, 4):
            # (T, C, Y, X)
            frame = stack[frame_idx].transpose(1, 2, 0) if not is_grayscale else stack[frame_idx, 0]
        else:
            # (T, Y, X, C)
            frame = stack[frame_idx]
        
        # Convert grayscale to BGR if needed (YOLO expects 3-channel)
        if is_grayscale or frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.ndim == 3 and frame.shape[2] == 1:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        
        # Run YOLO26 tracking on the frame, persisting tracks between frames
        result = model.track(frame, persist=True)[0]

        # Get the boxes and track IDs
        if result.boxes and result.boxes.is_track:
            boxes = result.boxes.xywh.cpu()
            track_ids = result.boxes.id.int().cpu().tolist()

            # Visualize the result on the frame
            frame = result.plot()

            # Plot the tracks
            for box, track_id in zip(boxes, track_ids):
                x, y, w, h = box
                track = track_history[track_id]
                track.append((float(x), float(y)))  # x, y center point
                if len(track) > 30:  # retain 30 tracks for 30 frames
                    track.pop(0)

                # Draw the tracking lines
                points = np.hstack(track).astype(np.int32).reshape((-1, 1, 2))
                cv2.polylines(frame, [points], isClosed=False, color=(230, 230, 230), thickness=10)

        # Display the annotated frame
        if show_display:
            cv2.imshow("YOLO26 Tracking", frame)
        
        # Print progress
        if (frame_idx + 1) % 10 == 0:
            print(f"Processed {frame_idx + 1}/{n_frames} frames")

        # # Break the loop if 'q' is pressed
        # if show_display and (cv2.waitKey(1) & 0xFF == ord("q")):
        #     break
        if show_display:
            key = cv2.waitKey(30) & 0xFF  # ~33 fps display
            if key == ord("q"):
                break

    # Close the display window
    if show_display:
        print("Press any key to close the window...")
        cv2.waitKey(0)  # Wait indefinitely until a key is pressed
        cv2.destroyAllWindows()
    print(f"Tracking complete! Processed {n_frames} frames.")
    
    return {"track_history": track_history}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Track cells in a TIFF stack using YOLO."
    )
    p.add_argument("--input", "-i", required=True, help="Path to input TIFF movie")
    p.add_argument(
        "--model",
        "-m",
        default="yolo26n.pt",
        help="Path to YOLO model (default: yolo26n.pt)",
    )
    p.add_argument(
        "--no-display",
        action="store_true",
        help="Disable display window (useful for headless/server runs)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    track_tiff(
        args.input,
        model_path=args.model,
        show_display=not args.no_display,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())