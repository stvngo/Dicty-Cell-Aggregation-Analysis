"""
Run a Roboflow workflow on each frame in data/jpg/waves and save outputs.

Requires ROBOFLOW_API_KEY in repo-root .env (see .env.template).

Usage:
  python roboflow/images/workflow.py              # resume in results/YYYY-MM-DD/
  python roboflow/images/workflow.py --fresh      # new folder results/YYYY-MM-DD_HHMMSS/
  python roboflow/images/workflow.py --no-resume  # re-run all frames in today's folder

Stop: Ctrl+C once (graceful). Ctrl+C twice (force exit).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import sys
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from inference_sdk import InferenceHTTPClient

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "roboflow" / "images" / "results"
load_dotenv(REPO_ROOT / ".env")

API_KEY = os.environ.get("ROBOFLOW_API_KEY")
WORKSPACE = os.environ.get("ROBOFLOW_WORKSPACE", "steven-ngo-s-workspace")
WORKFLOW_ID = os.environ.get("ROBOFLOW_WORKFLOW_ID", "kDVmXpKvaqfk4XFYHgCf")
INPUT_DIR = REPO_ROOT / "data" / "jpg" / "waves"
MAX_WORKERS = int(os.environ.get("ROBOFLOW_MAX_WORKERS", "10"))
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

OUTPUT_DIR: Path
SKIP_EXISTING = True
_stop_requested = False

if not API_KEY:
    raise SystemExit(
        "ROBOFLOW_API_KEY is not set. Copy .env.template to .env and add your API key."
    )

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=API_KEY,
)


def _request_stop(signum: int, frame) -> None:
    global _stop_requested
    if _stop_requested:
        print("\nForce quit.", file=sys.stderr)
        raise SystemExit(130)
    _stop_requested = True
    print(
        "\nStop requested — no new API calls. "
        "Waiting for in-flight requests (up to ~{n}). Ctrl+C again to force quit.".format(
            n=MAX_WORKERS
        ),
        file=sys.stderr,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch Roboflow workflow on wave frames.")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Write to a new timestamped folder (results/YYYY-MM-DD_HHMMSS).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Explicit output directory (overrides --fresh and default date folder).",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-call API for every frame even if outputs already exist in the output folder.",
    )
    return parser.parse_args()


def resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir is not None:
        return args.output_dir.resolve()
    if args.fresh:
        return RESULTS_ROOT / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return RESULTS_ROOT / date.today().isoformat()


def gather_image_paths(input_dir: Path) -> list[Path]:
    paths = [
        p
        for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(paths, key=lambda p: p.name)


def process_frame(image_path: Path) -> None:
    if _stop_requested:
        return

    stem = image_path.stem
    out_image = OUTPUT_DIR / f"{stem}.jpg"
    out_json = OUTPUT_DIR / f"{stem}.json"

    if SKIP_EXISTING and out_image.exists():
        print(f"Skip (exists): {out_image.name}")
        return

    try:
        result = client.run_workflow(
            workspace_name=WORKSPACE,
            workflow_id=WORKFLOW_ID,
            images={"image": str(image_path)},
            use_cache=True,
        )

        if _stop_requested:
            return

        output = result[0] if isinstance(result, list) else result

        b64_image = output.get("annotated_image")
        if b64_image:
            out_image.write_bytes(base64.b64decode(b64_image))
            print(f"Saved image: {out_image.name}")
        else:
            print(f"No annotated_image for {image_path.name}")

        with out_json.open("w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)

    except Exception as exc:
        if not _stop_requested:
            print(f"Error processing {image_path.name}: {exc}")


def main() -> None:
    global OUTPUT_DIR, SKIP_EXISTING

    args = parse_args()
    OUTPUT_DIR = resolve_output_dir(args)
    # Resume only when reusing today's folder and user did not ask to overwrite
    SKIP_EXISTING = not args.fresh and not args.no_resume

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    frames = gather_image_paths(INPUT_DIR)
    if not frames:
        raise SystemExit(f"No images found in {INPUT_DIR}")

    print(f"Input:  {INPUT_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Frames: {len(frames)} | workers: {MAX_WORKERS}")
    print(f"Resume: {SKIP_EXISTING} (skip frames that already have a .jpg)")
    print("Press Ctrl+C to stop (no new calls after first interrupt).")

    frame_iter = iter(frames)
    pending: set = set()
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for _ in range(min(MAX_WORKERS, len(frames))):
            try:
                pending.add(executor.submit(process_frame, next(frame_iter)))
            except StopIteration:
                break

        while pending and not _stop_requested:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()
                completed += 1
            while len(pending) < MAX_WORKERS and not _stop_requested:
                try:
                    pending.add(executor.submit(process_frame, next(frame_iter)))
                except StopIteration:
                    break

        if _stop_requested and pending:
            for future in pending:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

    if _stop_requested:
        print(f"Stopped early after {completed} completed frame(s).")
        raise SystemExit(130)

    print("Batch complete.")


if __name__ == "__main__":
    main()
