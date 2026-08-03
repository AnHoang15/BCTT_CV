"""Đếm đối tượng trong một vùng đa giác.

Bổ sung cho `CentroidCrossingCounter`. Vạch thẳng trả lời câu hỏi "bao nhiêu lượt đi
qua", còn vùng đa giác trả lời "hiện có bao nhiêu đối tượng bên trong" và "đã có bao
nhiêu đối tượng từng bước vào".

Dùng chung hai nguyên tắc với bộ đếm vạch:

- **Điểm neo là bàn chân**, không phải tâm hộp. Người đứng sát mép vùng có hộp phủ lên
  vùng nhưng chân vẫn ở ngoài; lấy tâm hộp sẽ tính nhầm là đã vào.
- **Debounce**: phải ở trong vùng liên tục vài khung hình mới tính là đã vào, tránh đếm
  lặp khi hộp rung quanh biên.
"""
from __future__ import annotations

import cv2
import numpy as np


class PolygonZoneCounter:
    """Theo dõi số đối tượng bên trong một vùng đa giác."""

    def __init__(self, points, anchor: str = "foot", debounce: int = 3,
                 max_age: int = 300, count_initial: bool = False) -> None:
        self.polygon = np.array(points, dtype=np.int32).reshape(-1, 1, 2)
        self.anchor = anchor
        self.debounce = max(1, debounce)
        self.max_age = max_age
        # Bình thường, đối tượng đã ở sẵn trong vùng lúc pipeline khởi động không tính
        # là "vừa vào". Luồng Thông minh thì ngược lại: vết chỉ hiện ra sau khi LA-3B
        # xác nhận, nên lần đầu nhìn thấy nó trong vùng là một lượt vào thật.
        self.count_initial = count_initial

        self.inside: dict[int, bool] = {}     # tid -> đang ở trong vùng (đã xác nhận)
        self.cand: dict[int, bool] = {}       # tid -> trạng thái ứng viên
        self.cand_cnt: dict[int, int] = {}
        self.last_seen: dict[int, int] = {}
        self.entered: set[int] = set()        # các vết đã từng vào, để không đếm trùng

        self.total_entered = 0
        self.current = 0
        self.last_events: list[dict] = []

    # ── nội bộ ───────────────────────────────────────────────────────────────
    def _anchor_pt(self, box) -> tuple[float, float]:
        cx = (box[0] + box[2]) / 2
        cy = box[3] if self.anchor == "foot" else (box[1] + box[3]) / 2
        return float(cx), float(cy)

    def _contains(self, point) -> bool:
        return cv2.pointPolygonTest(self.polygon, point, False) >= 0

    # ── API ──────────────────────────────────────────────────────────────────
    def reset(self) -> None:
        self.inside.clear()
        self.cand.clear()
        self.cand_cnt.clear()
        self.last_seen.clear()
        self.entered.clear()
        self.total_entered = 0
        self.current = 0
        self.last_events = []

    def update(self, boxes, tracker_ids, labels, frame_idx: int) -> list[dict]:
        """Cập nhật một khung hình. Trả về các lượt vừa bước vào vùng."""
        self.last_events = []
        if tracker_ids is None or len(tracker_ids) == 0:
            self.current = 0
            return self.last_events

        boxes = np.asarray(boxes, dtype=float)
        tracker_ids = [int(t) for t in tracker_ids]
        current_count = 0

        for index, tid in enumerate(tracker_ids):
            point = self._anchor_pt(boxes[index])
            raw = self._contains(point)
            self.last_seen[tid] = frame_idx

            if tid not in self.inside:
                self.inside[tid] = raw
                self.cand[tid] = raw
                self.cand_cnt[tid] = 0
                if raw and tid not in self.entered:
                    self.entered.add(tid)
                    if self.count_initial:
                        self.total_entered += 1
                        self.last_events.append({
                            "track_id": tid,
                            "direction": "in",
                            "label": (labels[index] if labels is not None
                                      and index < len(labels) else "person"),
                            "box": boxes[index].tolist(),
                        })
            else:
                if self.cand.get(tid) == raw:
                    self.cand_cnt[tid] += 1
                else:
                    self.cand[tid] = raw
                    self.cand_cnt[tid] = 1

                if raw != self.inside[tid] and self.cand_cnt[tid] >= self.debounce:
                    self.inside[tid] = raw
                    self.cand_cnt[tid] = 0
                    if raw and tid not in self.entered:
                        self.entered.add(tid)
                        self.total_entered += 1
                        self.last_events.append({
                            "track_id": tid,
                            "direction": "in",
                            "label": (labels[index] if labels is not None
                                      and index < len(labels) else "person"),
                            "box": boxes[index].tolist(),
                        })

            if self.inside.get(tid):
                current_count += 1

        self.current = current_count
        return self.last_events

    def prune(self, frame_idx: int) -> None:
        """Dọn vết không còn xuất hiện để bộ nhớ không phình theo thời gian chạy."""
        stale = [t for t, seen in self.last_seen.items()
                 if frame_idx - seen > self.max_age]
        for tid in stale:
            for store in (self.inside, self.cand, self.cand_cnt, self.last_seen):
                store.pop(tid, None)
            # `entered` giữ lại: vết quay lại sau đó không nên bị đếm thêm lần nữa.
