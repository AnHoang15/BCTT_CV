"""Bộ đếm đối tượng vượt vạch.

Cài đặt lại `CentroidCrossingCounter` — thuật toán đã được kiểm chứng trong giai đoạn
khảo sát. Ba điểm khác biệt so với `supervision.LineZone` mặc định:

1. **Điểm neo là bàn chân** (đáy hộp) thay vì tâm hộp. Người đi thẳng về phía camera có
   hộp to dần nên tâm hộp dao động lên xuống vắt qua vạch, gây đếm lặp. Đáy hộp di
   chuyển đơn điệu nên không bị.
2. **Vùng đệm (hysteresis) + debounce**: chỉ tính là đổi phía khi đối tượng vượt ra
   ngoài dải đệm quanh vạch và giữ nguyên phía mới trong ít nhất `debounce` khung hình.
3. **Nối lại track theo không gian**: khi ByteTrack đổi ID do che khuất, ID mới xuất
   hiện gần vị trí ID vừa mất sẽ được kế thừa lịch sử, tránh mất lượt đếm.
"""
from __future__ import annotations

from collections import deque

import numpy as np


def _as_point(p) -> np.ndarray:
    """Chấp nhận (x, y), [x, y] hoặc object có thuộc tính .x/.y."""
    if hasattr(p, "x") and hasattr(p, "y"):
        return np.array([p.x, p.y], dtype=float)
    return np.array(p, dtype=float)


class CentroidCrossingCounter:
    """Đếm số lượt đối tượng đi qua một đoạn thẳng, tách theo hai chiều Vào/Ra."""

    def __init__(
        self,
        line_start,
        line_end,
        history_len: int = 10,
        cooldown_frames: int = 20,
        relink_dist: float = 80,
        relink_frames: int = 15,
        anchor: str = "foot",
        margin_frac: float = 0.03,
        debounce: int = 3,
        flip: bool = False,
        directions: str = "both",
        count_labels: set[str] | None = None,
    ) -> None:
        self.p1 = _as_point(line_start)
        self.p2 = _as_point(line_end)
        self.line_vec = self.p2 - self.p1
        self.line_len_sq = float(np.dot(self.line_vec, self.line_vec)) + 1e-9
        self.line_len = self.line_len_sq ** 0.5

        self.history_len = history_len
        self.cooldown = cooldown_frames
        self.relink_dist = relink_dist
        self.relink_frames = relink_frames
        self.anchor = anchor
        # Vùng đệm tính theo CHIỀU CAO ĐỐI TƯỢNG, không theo độ dài vạch.
        #
        # Trước đây `margin = margin_frac * line_len`, và nó sai đơn vị. Vùng đệm sinh
        # ra để chống hộp giới hạn rung, mà biên độ rung tỉ lệ với kích thước đối tượng
        # trong ảnh chứ chẳng liên quan gì tới việc người dùng kéo vạch dài hay ngắn.
        # Đo được trên hai camera thật: cùng một thuật toán, vạch kéo hết khung 4K cho
        # biên 115px = 10% chiều cao người, còn vạch 1080px cho 32px = 22%. Hệ quả là
        # vẽ vạch dài hơn thì cùng một lượt đi qua lại không được đếm — người đi vào
        # cửa hàng vượt vạch 59px bị bỏ vì chưa đạt ngưỡng 115px.
        #
        # Lấy theo chiều cao hộp thì thang đo tự khớp với phối cảnh: người ở xa hộp nhỏ
        # cần biên nhỏ, người ở gần hộp to cần biên to, và kết quả không đổi khi người
        # dùng vẽ lại vạch dài ngắn khác nhau.
        #
        # Hệ số 3% đến từ đối chiếu với các lượt qua vạch đã xác minh bằng mắt trên năm
        # video mẫu. Mức 12% từng dùng nghe hợp lý nhưng quá rộng: người đứng sát camera
        # cao 1178px thì biên thành 141px, trong khi cả quãng bước vào cửa hàng chỉ đưa
        # bàn chân qua vạch được 60px — lượt vào cửa thật bị bỏ. Bằng chứng "đi qua thật"
        # không nên đến từ việc đi XA vạch, vì quãng đường vuông góc phụ thuộc góc đặt
        # camera; nó đến từ `history_len` khung làm mượt cộng `debounce` khung ở lại phía
        # mới. Vùng đệm chỉ cần đủ chặn nhiễu hộp giới hạn.
        self.margin_frac = margin_frac
        self.margin_min = 4.0
        self.debounce = max(1, debounce)
        self.flip = flip
        # Câu lệnh có thể chỉ quan tâm một chiều, ví dụ "đếm người đi vào". Lọc ngay
        # tại đây thay vì lọc danh sách sự kiện trả về, nếu không số đếm hiển thị sẽ
        # vẫn cộng cả chiều người dùng không yêu cầu.
        self.directions = directions if directions in ("both", "in", "out") else "both"
        # Lớp nào được cộng vào bộ đếm. `None` nghĩa là đếm tất cả.
        #
        # Camera ghi nhận mọi lớp mô hình nhận ra, vì một lượt suy luận YOLO đã tính
        # sẵn cả tám mươi lớp rồi — lọc bớt chỉ là vứt kết quả đi chứ không tiết kiệm
        # được gì (đo được: chênh 2,5%, nằm trong sai số). Nhưng bộ đếm hiển thị thì
        # phải đúng thứ người dùng yêu cầu, nên hai việc tách riêng.
        self.count_labels = set(count_labels) if count_labels else None

        self.centroids: dict[int, deque] = {}   # tid -> lịch sử điểm neo
        self.sides: dict[int, int] = {}         # tid -> phía đã xác nhận (+1/-1)
        self.cand: dict[int, int] = {}          # tid -> phía ứng viên
        self.cand_cnt: dict[int, int] = {}      # tid -> số khung giữ ứng viên
        self.last_seen: dict[int, int] = {}
        self.counted: dict[int, int] = {}

        self.in_count = 0
        self.out_count = 0
        # Lượt vừa phát sinh trong lần update gần nhất — worker dùng để ghi sự kiện.
        self.last_events: list[dict] = []

    # ── nội bộ ───────────────────────────────────────────────────────────────
    def _anchor_pt(self, box) -> np.ndarray:
        cx = (box[0] + box[2]) / 2
        cy = box[3] if self.anchor == "foot" else (box[1] + box[3]) / 2
        return np.array([cx, cy], dtype=float)

    def _margin_for(self, box) -> float:
        """Bề rộng vùng đệm cho riêng một đối tượng, theo chiều cao hộp của nó."""
        return max(self.margin_min, self.margin_frac * float(box[3] - box[1]))

    def _signed_distance(self, pt: np.ndarray) -> float:
        """Khoảng cách có dấu từ điểm tới đường thẳng chứa vạch."""
        return (
            self.line_vec[0] * (pt[1] - self.p1[1])
            - self.line_vec[1] * (pt[0] - self.p1[0])
        ) / self.line_len

    def _on_segment(self, pt: np.ndarray) -> bool:
        """Hình chiếu của điểm có nằm trong phạm vi đoạn vạch không."""
        t = float(np.dot(pt - self.p1, self.line_vec) / self.line_len_sq)
        return 0.0 <= t <= 1.0

    # ── API ──────────────────────────────────────────────────────────────────
    def reset(self) -> None:
        self.centroids.clear()
        self.sides.clear()
        self.cand.clear()
        self.cand_cnt.clear()
        self.last_seen.clear()
        self.counted.clear()
        self.in_count = 0
        self.out_count = 0
        self.last_events = []

    def update(self, boxes, tracker_ids, labels, frame_idx: int) -> list[dict]:
        """Cập nhật một khung hình. Trả về danh sách lượt vượt vạch mới phát sinh."""
        self.last_events = []
        if tracker_ids is None or len(tracker_ids) == 0:
            return self.last_events

        boxes = np.asarray(boxes, dtype=float)
        tracker_ids = [int(t) for t in tracker_ids]
        current_ids = set(tracker_ids)

        # ── Nối lại ID mới với ID vừa mất ở gần ──────────────────────────────
        recently_lost = {
            tid
            for tid, seen in self.last_seen.items()
            if tid not in current_ids
            and 0 < frame_idx - seen <= self.relink_frames
            and len(self.centroids.get(tid, ())) >= 3
        }
        for i, tid in enumerate(tracker_ids):
            if tid in self.centroids:
                continue
            new_pt = self._anchor_pt(boxes[i])
            best_dist, best_lost = self.relink_dist, None
            for lost in recently_lost:
                d = float(np.linalg.norm(new_pt - self.centroids[lost][-1]))
                if d < best_dist:
                    best_dist, best_lost = d, lost
            if best_lost is not None:
                for store in (self.centroids, self.sides, self.cand,
                              self.cand_cnt, self.counted):
                    if best_lost in store:
                        store[tid] = store.pop(best_lost)
                recently_lost.discard(best_lost)

        # ── Cập nhật lịch sử và kiểm tra vượt vạch ───────────────────────────
        for i, tid in enumerate(tracker_ids):
            pt = self._anchor_pt(boxes[i])
            if tid not in self.centroids:
                self.centroids[tid] = deque(maxlen=self.history_len)
            self.centroids[tid].append(pt)
            self.last_seen[tid] = frame_idx

            smooth = np.mean(list(self.centroids[tid]), axis=0)
            dist = self._signed_distance(smooth)

            if self.sides.get(tid) is None:
                # Khung đầu tiên: chốt phía ban đầu, chưa đếm.
                self.sides[tid] = 1 if dist >= 0 else -1
                self.cand[tid] = self.sides[tid]
                self.cand_cnt[tid] = 0
                continue

            # 0 = còn trong vùng đệm, chưa coi là đã sang phía khác.
            margin = self._margin_for(boxes[i])
            raw = 1 if dist > margin else (-1 if dist < -margin else 0)
            if raw == 0 or raw == self.sides[tid]:
                self.cand[tid] = self.sides[tid]
                self.cand_cnt[tid] = 0
                continue

            if self.cand.get(tid) == raw:
                self.cand_cnt[tid] += 1
            else:
                self.cand[tid] = raw
                self.cand_cnt[tid] = 1

            crossed = (
                self.cand_cnt[tid] >= self.debounce
                and frame_idx - self.counted.get(tid, -self.cooldown) >= self.cooldown
                and self._on_segment(smooth)
            )
            if not crossed:
                continue

            direction = "in" if ((raw == 1) != self.flip) else "out"

            # Phía mới luôn được ghi nhận, kể cả khi chiều này không được đếm — nếu
            # không, vết sẽ kẹt ở phía cũ và đếm lặp mỗi khung hình.
            self.counted[tid] = frame_idx
            self.sides[tid] = raw
            self.cand_cnt[tid] = 0

            label = labels[i] if labels is not None and i < len(labels) else "person"

            # Ghi nhận mọi lượt cắt vạch, nhưng chỉ cộng vào bộ đếm những lượt khớp
            # cả lớp đối tượng lẫn chiều mà người dùng chọn.
            #
            # Tách hai việc này ra vì chúng vốn là hai câu hỏi khác nhau: "camera thấy
            # gì" và "tôi muốn đếm gì". Trước đây gộp làm một, nên pipeline đặt "chỉ
            # đếm vào" thì mọi lượt đi ra bị vứt thẳng — về sau tìm "người đi ra hôm
            # nay" trên camera đó không ra gì, dù hệ thống đã nhìn thấy đủ cả.
            dung_chieu = self.directions == "both" or direction == self.directions
            dung_lop = self.count_labels is None or label in self.count_labels
            if dung_chieu and dung_lop:
                if direction == "in":
                    self.in_count += 1
                else:
                    self.out_count += 1

            self.last_events.append({
                "track_id": tid,
                "direction": direction,
                "label": label,
                "counted": dung_chieu and dung_lop,
                "box": boxes[i].tolist(),
            })

        return self.last_events

    def prune(self, frame_idx: int, max_age: int = 300) -> None:
        """Dọn track không còn xuất hiện để bộ nhớ không phình theo thời gian chạy."""
        stale = [t for t, seen in self.last_seen.items() if frame_idx - seen > max_age]
        for tid in stale:
            for store in (self.centroids, self.sides, self.cand,
                          self.cand_cnt, self.last_seen, self.counted):
                store.pop(tid, None)
