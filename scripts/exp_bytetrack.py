#!/usr/bin/env python3
"""Thực nghiệm 2 — Ảnh hưởng của minimum_matching_threshold tới độ bền của vết.

Sinh số liệu cho Bảng "Ngưỡng ghép vết quyết định độ bền của track" ở Chương 3.

Ngưỡng này áp lên chi phí `1 - IoU`, nên ngưỡng CÀNG NHỎ thì yêu cầu chồng lấn
CÀNG CAO. Đặt 0,3 tức là đòi IoU >= 0,7 giữa hai khung liên tiếp.

    python scripts/exp_bytetrack.py <video> [số_khung=480] [khung_bắt_đầu=0]
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import supervision as sv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.counter import CentroidCrossingCounter                    # noqa: E402
from app.detector import apply_nms, filter_min_size, get_model     # noqa: E402

THRESHOLDS = (0.3, 0.5, 0.7, 0.8, 0.9)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    video = sys.argv[1]
    max_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 480
    start = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    probe = cv2.VideoCapture(video)
    if not probe.isOpened():
        print(f"Không mở được video: {video}")
        sys.exit(1)
    width = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = probe.get(cv2.CAP_PROP_FPS) or 30
    probe.release()

    model = get_model()
    print(f"{Path(video).name}  {width}x{height} @{fps:.0f}fps  "
          f"khung {start}..{start + max_frames}\n")
    print(f"{'Ngưỡng':>8} {'IoU tối thiểu':>14} {'Số ID':>7} "
          f"{'Trung vị':>9} {'Dài nhất':>9} {'Vào':>5} {'Ra':>4}")
    print("-" * 62)

    for threshold in THRESHOLDS:
        cap = cv2.VideoCapture(video)
        if start:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start)

        tracker = sv.ByteTrack(
            frame_rate=int(fps),
            track_activation_threshold=0.20,
            lost_track_buffer=50,
            minimum_matching_threshold=threshold,
            minimum_consecutive_frames=1,
        )
        counter = CentroidCrossingCounter(
            (0, 0.60 * height), (width, 0.60 * height), anchor="foot"
        )
        lifetime: dict[int, int] = defaultdict(int)

        for index in range(max_frames):
            ok, frame = cap.read()
            if not ok:
                break
            result = model(frame, classes=[0], conf=0.25, imgsz=960, verbose=False)[0]
            dets = filter_min_size(apply_nms(sv.Detections.from_ultralytics(result)))
            dets = tracker.update_with_detections(dets)
            if dets.tracker_id is None or len(dets) == 0:
                continue
            track_ids = [int(t) for t in dets.tracker_id]
            for tid in track_ids:
                lifetime[tid] += 1
            counter.update(dets.xyxy, track_ids, ["person"] * len(dets), index)

        cap.release()
        lengths = sorted(lifetime.values()) or [0]
        print(f"{threshold:>8.1f} {1 - threshold:>14.1f} {len(lifetime):>7} "
              f"{statistics.median(lengths):>9.0f} {max(lengths):>9} "
              f"{counter.in_count:>5} {counter.out_count:>4}")


if __name__ == "__main__":
    main()
