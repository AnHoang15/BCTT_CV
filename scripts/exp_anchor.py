#!/usr/bin/env python3
"""Thực nghiệm 1 — So sánh điểm neo bàn chân với tâm hộp, quét nhiều vị trí vạch.

Sinh số liệu cho Bảng "Điểm neo bàn chân loại bỏ hiện tượng đếm dư" ở Chương 3.

    python scripts/exp_anchor.py <video> [số_khung=480] [khung_bắt_đầu=0]

Ví dụ:
    python scripts/exp_anchor.py videos/walkback.mp4 480 0
"""
from __future__ import annotations

import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.counter import CentroidCrossingCounter  # noqa: E402
from app.detector import Detector, get_model     # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    video = sys.argv[1]
    max_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 480
    start = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        print(f"Không mở được video: {video}")
        sys.exit(1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    if start:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)

    print(f"Video: {Path(video).name}  {width}x{height} @{fps:.0f}fps  "
          f"(khung {start}..{start + max_frames})")
    get_model()

    lines = {
        "Ngang 40%": ((0, 0.40 * height), (width, 0.40 * height)),
        "Ngang 50%": ((0, 0.50 * height), (width, 0.50 * height)),
        "Ngang 60%": ((0, 0.60 * height), (width, 0.60 * height)),
        "Ngang 70%": ((0, 0.70 * height), (width, 0.70 * height)),
        "Dọc 30%":   ((0.30 * width, 0), (0.30 * width, height)),
        "Dọc 50%":   ((0.50 * width, 0), (0.50 * width, height)),
        "Dọc 70%":   ((0.70 * width, 0), (0.70 * width, height)),
    }

    detector = Detector(["person"], fps=fps)
    # Cột "bàn chân": cấu hình mặc định của hệ thống.
    foot = {k: CentroidCrossingCounter(a, b, anchor="foot")
            for k, (a, b) in lines.items()}
    # Cột "tâm hộp": tắt vùng đệm và độ trễ xác nhận để tái hiện LineZone nguyên bản.
    center = {k: CentroidCrossingCounter(a, b, anchor="center",
                                         margin_frac=0.0, debounce=1)
              for k, (a, b) in lines.items()}

    lifetime: dict[int, int] = defaultdict(int)
    frames = 0
    started = time.time()

    while frames < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        boxes, track_ids, labels, _ = detector(frame)
        for tid in track_ids:
            lifetime[tid] += 1
        for counter in (*foot.values(), *center.values()):
            counter.update(boxes, track_ids, labels, frames)
        frames += 1

    elapsed = time.time() - started
    cap.release()

    lengths = sorted(lifetime.values()) or [0]
    print(f"\nXử lý {frames} khung trong {elapsed:.1f}s  →  {frames / elapsed:.1f} fps")
    print(f"Số mã định danh: {len(lifetime)}")
    print(f"Độ dài vết: trung vị {statistics.median(lengths):.0f} khung, "
          f"dài nhất {max(lengths)} khung")

    print(f"\n{'Vị trí vạch':<12} {'CHÂN Vào':>9} {'CHÂN Ra':>8} "
          f"{'TÂM Vào':>9} {'TÂM Ra':>8}")
    print("-" * 50)
    for key in lines:
        f, c = foot[key], center[key]
        print(f"{key:<12} {f.in_count:>9} {f.out_count:>8} "
              f"{c.in_count:>9} {c.out_count:>8}")


if __name__ == "__main__":
    main()
