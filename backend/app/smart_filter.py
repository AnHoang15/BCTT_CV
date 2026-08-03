"""Bộ lọc Thông minh: dùng LocateAnything-3B lọc đối tượng theo mô tả tiếng Việt.

Vấn đề cốt lõi là tốc độ. LA-3B mất khoảng một giây cho mỗi khung cắt, trong khi vòng
lặp camera chạy 15 khung hình mỗi giây. Gọi trực tiếp trong vòng lặp sẽ làm luồng video
đứng hình.

Cách giải quyết gồm ba phần:

1. **Hỏi một lần cho mỗi vết.** Kết quả lưu theo mã định danh. Một người xuất hiện
   trong 300 khung hình chỉ tốn đúng một lần gọi LA-3B.
2. **Gọi bất đồng bộ theo lô.** Một luồng phụ xử lý hàng đợi khung cắt; vòng lặp chính
   không bao giờ chờ. Luồng phụ vét hàng đợi để hỏi nhiều khung cắt trong một lời gọi,
   vì trên Apple Silicon mọi lời gọi GPU đều phải xếp hàng chung với YOLO — hỏi lẻ
   từng cái làm luồng video của các camera khác bị chặn liên tục.
3. **Đệm lượt vượt vạch.** Trong lúc chờ phán quyết, vết vẫn có thể đi qua vạch. Các
   lượt đó được ghi tạm; khi LA-3B xác nhận khớp thì mới cộng vào bộ đếm, còn không
   thì bỏ. Thiếu bước này, mọi lượt vượt vạch xảy ra trong khoảng một giây đầu tiên
   của mỗi vết đều bị mất.
"""
from __future__ import annotations

import queue
import threading
from collections import defaultdict

import numpy as np

from . import config, locate_anything


class SmartFilter:
    """Lọc các vết theo mô tả ngôn ngữ tự nhiên, chạy bất đồng bộ."""

    def __init__(self, query: str, line_p1, line_p2, flip: bool = False) -> None:
        self.query = query
        self.flip = flip

        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()

        self.verdict: dict[int, bool] = {}      # tid -> đã khớp hay không
        self.pending: set[int] = set()          # tid đang chờ phán quyết
        self.pending_crossings: dict[int, int] = defaultdict(int)
        self.prev_side: dict[int, int] = {}
        self.calls = 0

        # Hình học của vạch, dùng để theo dõi phía của các vết đang chờ.
        self._p1 = np.asarray(line_p1, dtype=float)
        vec = np.asarray(line_p2, dtype=float) - self._p1
        self._vec = vec
        self._len = float(np.hypot(*vec)) or 1.0

        # Bộ đếm nhận lượt đã được xác nhận; do worker gọi ngược lại.
        self.on_confirmed = None

        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="la3b-worker"
        )
        self._thread.start()

    # ── Luồng phụ ────────────────────────────────────────────────────────────
    def _drain(self, first) -> tuple[list[int], list]:
        """Gom `first` cùng những khung cắt đã xếp hàng thành một lô.

        Ở cảnh đông người, vết mới sinh ra thành cụm nên hàng đợi gần như luôn có
        sẵn vài khung cắt. Hỏi cả cụm trong một lời gọi rẻ hơn hẳn hỏi lẻ từng cái,
        và quan trọng hơn là giữ khoá GPU ít lần hơn nên camera bớt bị chặn.
        """
        tids, crops = [first[0]], [first[1]]
        while len(crops) < max(1, config.LA_BATCH_SIZE):
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:                       # tín hiệu dừng, trả lại rồi thoát
                self._queue.put(None)
                self._queue.task_done()
                break
            tids.append(item[0])
            crops.append(item[1])
        return tids, crops

    def _worker(self) -> None:
        while not self._stop.is_set():
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break

            tids, crops = self._drain(item)
            try:
                results = locate_anything.match(
                    crops, self.query,
                    temperature=config.LA_TEMPERATURE,
                    votes=config.LA_VOTES,
                    batch_size=config.LA_BATCH_SIZE,
                )
            except Exception as exc:
                print(f"[TM] Lỗi khi hỏi LA-3B cho {len(tids)} vết: {exc}")
                results = [False] * len(tids)

            confirmed: list[tuple[int, int]] = []
            with self._lock:
                for tid, matched in zip(tids, results):
                    self.verdict[tid] = matched
                    self.pending.discard(tid)
                    net = self.pending_crossings.pop(tid, 0)
                    if matched and net:
                        confirmed.append((tid, net))

            # Gọi ngoài vùng khoá để không giữ khoá trong lúc ghi cơ sở dữ liệu.
            if self.on_confirmed:
                for tid, net in confirmed:
                    self.on_confirmed(tid, net)
            for _ in tids:
                self._queue.task_done()

    # ── Vòng lặp chính gọi vào ───────────────────────────────────────────────
    def _side_of(self, box) -> int:
        """Phía của điểm chân so với vạch: +1 hoặc -1."""
        foot_x = (box[0] + box[2]) / 2
        foot_y = box[3]
        dist = (self._vec[0] * (foot_y - self._p1[1])
                - self._vec[1] * (foot_x - self._p1[0])) / self._len
        return 1 if dist >= 0 else -1

    def apply(self, frame, boxes, track_ids: list[int]) -> np.ndarray:
        """Trả về mặt nạ giữ lại các vết đã được xác nhận khớp mô tả.

        Vết đang chờ phán quyết tạm thời bị ẩn khỏi bộ đếm, nhưng lượt vượt vạch của
        chúng vẫn được ghi lại để cộng bù sau.
        """
        if not track_ids:
            return np.zeros(0, dtype=bool)

        with self._lock:
            for index, tid in enumerate(track_ids):
                if tid not in self.verdict and tid not in self.pending:
                    crop = locate_anything.crop_to_pil(
                        frame, boxes[index], config.LA_CROP_SIZE
                    )
                    if crop is None:
                        self.verdict[tid] = False
                        continue
                    self.pending.add(tid)
                    self.calls += 1
                    self._queue.put((tid, crop))

                if tid in self.pending:
                    side = self._side_of(boxes[index])
                    previous = self.prev_side.get(tid)
                    if previous is not None and previous != side:
                        delta = 1 if side > 0 else -1
                        if self.flip:
                            delta = -delta
                        self.pending_crossings[tid] += delta
                    self.prev_side[tid] = side

            return np.array(
                [self.verdict.get(tid, False) for tid in track_ids], dtype=bool
            )

    def stats(self) -> dict:
        with self._lock:
            matched = sum(1 for v in self.verdict.values() if v)
            return {
                "la_calls": self.calls,
                "la_pending": len(self.pending),
                "la_matched": matched,
                "la_rejected": len(self.verdict) - matched,
            }

    def reset(self) -> None:
        with self._lock:
            self.verdict.clear()
            self.pending.clear()
            self.pending_crossings.clear()
            self.prev_side.clear()
            self.calls = 0

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        self._thread.join(timeout=3)
