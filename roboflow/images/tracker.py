"""
Track wave instance polygons and render a 60 fps MP4 from original wave frames.

Two modes:
  --offline   Use saved per-frame JSON + data/jpg/waves (no API). Local ByteTrack on boxes.
  --stream    Roboflow Video Stream API + tracking workflow (trajectory_data + predictions).

Tracking note (SORT vs ByteTrack / BoT-SORT):
  - SORT: Kalman + IoU only; fine for 0–3 slow blobs, but IDs swap when regions overlap.
  - ByteTrack (supervision): stronger association for low-FPS boxes + missed frames; recommended here.
  - Roboflow tracking workflow may already emit trajectory_data; offline ByteTrack aligns JSON exports.

Examples:
  python roboflow/images/tracker.py --offline \\
    --results-dir roboflow/images/results/2026-05-16_232640 \\
    --waves-dir data/jpg/waves \\
    --output roboflow/images/results/2026-05-16_232640/tracked_60fps.mp4

  python roboflow/images/tracker.py --stream \\
    --video roboflow/images/waves_60fps.mp4 \\
    --output roboflow/images/results/tracked_stream_60fps.mp4
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
import supervision as sv
from dotenv import load_dotenv
from PIL import Image

_IMAGES_DIR = Path(__file__).resolve().parent
if str(_IMAGES_DIR) not in sys.path:
    sys.path.insert(0, str(_IMAGES_DIR))

from wave_geometry import (
    frame_index_from_name,
    is_wave_segmentation,
    parse_predictions_blob,
    polygon_metrics,
    points_to_contour,
    prediction_to_xyxy,
    sorted_wave_frames,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

API_KEY = os.environ.get("ROBOFLOW_API_KEY")
WORKSPACE = os.environ.get("ROBOFLOW_WORKSPACE", "steven-ngo-s-workspace")
TRACKING_WORKFLOW = os.environ.get(
    "ROBOFLOW_TRACKING_WORKFLOW_ID",
    "dicty-waves-tracking-workflow-1779016051221",
)
TRAIL_LENGTH = 30


def _color_for_track(track_id: int) -> tuple[int, int, int]:
    palette = sv.ColorPalette.default()
    color = palette.by_idx(int(track_id) if track_id is not None else 0)
    return (int(color.b), int(color.g), int(color.r))


def _load_bgr(path: Path) -> np.ndarray:
    img = np.asarray(Image.open(path))
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return cv2.cvtColor(img[..., :3], cv2.COLOR_RGB2BGR)


def _predictions_to_detections(preds: list[dict]) -> sv.Detections:
    valid = [p for p in preds if is_wave_segmentation(p)]
    if not valid:
        return sv.Detections.empty()
    xyxy = np.stack([prediction_to_xyxy(p) for p in valid], axis=0)
    conf = np.array([float(p.get("confidence", 1.0)) for p in valid], dtype=np.float32)
    class_id = np.array([int(p.get("class_id", 0)) for p in valid], dtype=int)
    return sv.Detections(xyxy=xyxy, confidence=conf, class_id=class_id)


def _valid_preds_for_draw(preds: list[dict]) -> list[dict]:
    return [p for p in preds if is_wave_segmentation(p)]


def _draw_overlay(
    frame_bgr: np.ndarray,
    preds: list[dict],
    track_ids: list[int | None],
    trails: dict[int, deque[tuple[int, int]]],
) -> np.ndarray:
    out = frame_bgr.copy()
    overlay = out.copy()

    for pred, tid in zip(preds, track_ids):
        points = pred.get("points") or []
        if len(points) < 3:
            continue
        area, peri, cx, cy = polygon_metrics(points)
        contour = points_to_contour(points).astype(np.int32)
        color = _color_for_track(tid if tid is not None else 0)

        cv2.fillPoly(overlay, [contour], color)
        cv2.polylines(out, [contour], isClosed=True, color=color, thickness=2)

        label_tid = "—" if tid is None else str(int(tid))
        label = f"id {label_tid}  A={area:.0f}px2  P={peri:.0f}px"
        tx, ty = int(cx), int(cy)
        cv2.putText(
            out,
            label,
            (max(4, tx - 80), max(16, ty - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

        if tid is not None:
            trails[tid].append((int(cx), int(cy)))

    cv2.addWeighted(overlay, 0.25, out, 0.75, 0, out)

    for tid, path in trails.items():
        if len(path) < 2:
            continue
        pts = np.array(path, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], isClosed=False, color=_color_for_track(tid), thickness=2)

    return out


def run_offline(
    results_dir: Path,
    waves_dir: Path,
    output_path: Path,
    fps: float,
    max_frames: int | None = None,
) -> None:
    wave_paths = sorted_wave_frames(waves_dir)
    if max_frames is not None:
        wave_paths = wave_paths[:max_frames]
    if not wave_paths:
        raise SystemExit(f"No images in {waves_dir}")

    json_by_idx = {}
    for jp in results_dir.glob("*.json"):
        json_by_idx[frame_index_from_name(jp.name)] = jp

    tracker = sv.ByteTrack()
    trails: dict[int, deque[tuple[int, int]]] = defaultdict(
        lambda: deque(maxlen=TRAIL_LENGTH)
    )

    first = _load_bgr(wave_paths[0])
    h, w = first.shape[:2]
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (w, h),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Cannot open VideoWriter for {output_path}")

    print(f"Offline: {len(wave_paths)} frames, {len(json_by_idx)} JSON files")
    print(f"Tracker: ByteTrack (supervision) | output @ {fps} fps")

    for i, wave_path in enumerate(wave_paths):
        idx = frame_index_from_name(wave_path.name)
        frame = _load_bgr(wave_path)

        preds: list[dict] = []
        json_path = json_by_idx.get(idx)
        if json_path and json_path.exists():
            blob = json.loads(json_path.read_text(encoding="utf-8"))
            preds = parse_predictions_blob(blob)

        valid = _valid_preds_for_draw(preds)
        if valid:
            detections = _predictions_to_detections(valid)
            detections = tracker.update_with_detections(detections)
            track_ids = (
                [None] * len(valid)
                if detections.tracker_id is None
                else [int(t) if t is not None else None for t in detections.tracker_id]
            )
            painted = _draw_overlay(frame, valid, track_ids, trails)
        else:
            painted = frame
        writer.write(painted)

        if (i + 1) % 200 == 0 or i + 1 == len(wave_paths):
            print(f"  {i + 1}/{len(wave_paths)} frame {idx} | {len(preds)} waves")

    writer.release()
    print(f"Saved {output_path}")


def _decode_stream_image(field) -> np.ndarray | None:
    if field is None:
        return None
    if isinstance(field, dict):
        b64 = field.get("value", field.get("image"))
    else:
        b64 = field
    if not b64:
        return None
    raw = base64.b64decode(b64)
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def _extract_predictions_from_stream(data: dict) -> list[dict]:
    if "predictions" not in data:
        return []
    raw = data["predictions"]
    if isinstance(raw, dict) and "value" in raw:
        raw = raw["value"]
    if isinstance(raw, dict):
        items = parse_predictions_blob({"predictions": raw})
    elif isinstance(raw, list):
        items = [p for p in raw if is_wave_segmentation(p)]
    else:
        items = []
    return items


def run_stream(
    video_path: Path,
    output_path: Path,
    fps: float,
    waves_dir: Path | None,
) -> None:
    if not API_KEY:
        raise SystemExit("ROBOFLOW_API_KEY missing in .env")

    try:
        from inference_sdk import InferenceHTTPClient
        from inference_sdk.webrtc import StreamConfig, VideoFileSource, VideoMetadata
    except ImportError as exc:
        raise SystemExit(
            "Video stream mode requires inference-sdk with WebRTC extras. "
            "Install with: pip install 'inference-sdk[webrtc]'"
        ) from exc

    wave_paths = sorted_wave_frames(waves_dir) if waves_dir else []
    wave_by_idx = {frame_index_from_name(p.name): p for p in wave_paths}

    client = InferenceHTTPClient(
        api_url="https://serverless.roboflow.com",
        api_key=API_KEY,
    )

    config = StreamConfig(
        stream_output=[],
        data_output=["predictions", "trajectory_data"],
        requested_plan="webrtc-gpu-medium",
        requested_region="us",
    )

    session = client.webrtc.stream(
        source=VideoFileSource(str(video_path), realtime_processing=False),
        workflow=TRACKING_WORKFLOW,
        workspace=WORKSPACE,
        image_input="image",
        config=config,
    )

    tracker = sv.ByteTrack()
    trails: dict[int, deque[tuple[int, int]]] = defaultdict(
        lambda: deque(maxlen=TRAIL_LENGTH)
    )
    stream_trajectories: list[dict] = []
    writer: cv2.VideoWriter | None = None
    frame_count = 0

    @session.on_data()
    def on_data(data: dict, metadata: VideoMetadata) -> None:
        nonlocal writer, frame_count

        try:
            fid = int(metadata.frame_id)
            preds = _extract_predictions_from_stream(data)
            valid = _valid_preds_for_draw(preds)

            if wave_by_idx and fid in wave_by_idx:
                frame = _load_bgr(wave_by_idx[fid])
            else:
                frame = np.zeros((512, 512, 3), dtype=np.uint8)

            detections = _predictions_to_detections(valid)
            detections = tracker.update_with_detections(detections)
            track_ids = (
                [None] * len(valid)
                if detections.tracker_id is None
                else [int(t) if t is not None else None for t in detections.tracker_id]
            )

            if "trajectory_data" in data:
                traj = data["trajectory_data"]
                if isinstance(traj, dict):
                    traj = traj.get("value", traj)
                if isinstance(traj, list):
                    for item in traj:
                        if isinstance(item, dict):
                            stream_trajectories.append({"frame_id": fid, **item})

            painted = _draw_overlay(frame, valid, track_ids, trails)

            if writer is None:
                h, w = painted.shape[:2]
                output_path.parent.mkdir(parents=True, exist_ok=True)
                writer = cv2.VideoWriter(
                    str(output_path),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    fps,
                    (w, h),
                )

            writer.write(painted)
            frame_count += 1
            if frame_count % 100 == 0:
                print(f"  stream frame {fid} ({len(valid)} waves, {frame_count} written)")
        except Exception as exc:
            print(f"  [warn] frame {metadata.frame_id}: {exc}", file=sys.stderr)

    print(f"Streaming {video_path} via workflow {TRACKING_WORKFLOW}")
    session.run()

    if writer is not None:
        writer.release()

    traj_path = output_path.with_suffix(".trajectories.json")
    traj_path.write_text(json.dumps(stream_trajectories, indent=2), encoding="utf-8")
    print(f"Saved {output_path} ({frame_count} frames)")
    print(f"Saved {traj_path}")


def ensure_waves_video(waves_dir: Path, video_path: Path, fps: float) -> Path:
    if video_path.exists():
        return video_path
    print(f"Building {video_path} from {waves_dir} @ {fps} fps ...")
    preproc = REPO_ROOT / "preprocessor"
    if str(preproc) not in sys.path:
        sys.path.insert(0, str(preproc))
    from jpgs_to_mp4 import jpgs_to_mp4

    jpgs_to_mp4(waves_dir, video_path, fps=fps)
    return video_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track waves and render annotated MP4.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--offline",
        action="store_true",
        help="Use saved JSON + original wave JPGs (recommended with existing results).",
    )
    mode.add_argument(
        "--stream",
        action="store_true",
        help="Roboflow Video Stream API + tracking workflow.",
    )
    parser.add_argument("--results-dir", type=Path, default=None)
    parser.add_argument("--waves-dir", type=Path, default=REPO_ROOT / "data" / "jpg" / "waves")
    parser.add_argument("--video", type=Path, default=REPO_ROOT / "roboflow" / "images" / "waves_60fps.mp4")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=60.0, help="Output video FPS (default 60).")
    parser.add_argument("--max-frames", type=int, default=None, help="Process only first N frames (debug).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = args.output.resolve()

    if args.offline:
        if not args.results_dir:
            raise SystemExit("--results-dir is required for --offline")
        run_offline(
            args.results_dir.resolve(),
            args.waves_dir.resolve(),
            output_path,
            args.fps,
            max_frames=args.max_frames,
        )
    else:
        video_path = ensure_waves_video(args.waves_dir.resolve(), args.video.resolve(), args.fps)
        run_stream(video_path, output_path, args.fps, args.waves_dir.resolve())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
