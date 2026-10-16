import cv2
import base64
import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from inference_sdk import InferenceHTTPClient
from inference_sdk.webrtc import VideoFileSource, StreamConfig, VideoMetadata

# Requires ROBOFLOW_API_KEY in repo-root .env (see .env.template).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
API_KEY = os.environ.get("ROBOFLOW_API_KEY")
WORKSPACE = os.environ.get("ROBOFLOW_WORKSPACE", "steven-ngo-s-workspace")
if not API_KEY:
    raise SystemExit("ROBOFLOW_API_KEY is not set. Copy .env.template to .env and add your API key.")

client = InferenceHTTPClient.init(
    api_url="https://serverless.roboflow.com",
    api_key=API_KEY,
)

source = VideoFileSource("path/to/your/video.mp4", realtime_processing=False)  # Buffer and process all frames

VIDEO_OUTPUT = "annotated_image"
DATA_OUTPUTS = ["predictions"]

config = StreamConfig(
    stream_output=[], # We request all data via data_output for video files
    data_output=["annotated_image","predictions"],
    requested_plan="webrtc-gpu-medium",
    requested_region="us",
)

session = client.webrtc.stream(
    source=source,
    workflow="dicty-waves-batch-segmentation-1778982537120",
    workspace=WORKSPACE,
    image_input="image",
    config=config
)

frames = []

@session.on_data()
def on_data(data: dict, metadata: VideoMetadata):
    # print(f"Frame {metadata.frame_id} predictions: {data}")
    
    if VIDEO_OUTPUT and VIDEO_OUTPUT in data:
        timestamp_ms = metadata.pts * metadata.time_base * 1000
        img = cv2.imdecode(np.frombuffer(base64.b64decode(data[VIDEO_OUTPUT]["value"]), np.uint8), cv2.IMREAD_COLOR)
        frames.append((timestamp_ms, metadata.frame_id, img))
        print(f"Processed frame {metadata.frame_id}")
    else:
        print(f"Processed frame {metadata.frame_id} (data only)")

session.run()

if VIDEO_OUTPUT and len(frames) > 0:
    # Stitch frames into output video
    frames.sort(key=lambda x: x[1])
    fps = (len(frames) - 1) / ((frames[-1][0] - frames[0][0]) / 1000) if len(frames) > 1 else 30.0
    h, w = frames[0][2].shape[:2]
    out = cv2.VideoWriter("output.mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for _, _, frame in frames:
        out.write(frame)
    out.release()
    print(f"Done! {len(frames)} frames at {fps:.1f} FPS -> output.mp4")
elif VIDEO_OUTPUT:
    print("No video frames collected.")
