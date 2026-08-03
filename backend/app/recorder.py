"""Ghi hình liên tục thành từng đoạn ngắn để phục vụ chức năng xem lại.

Ghi thành nhiều tệp ngắn (mặc định 60 giây) thay vì một tệp dài có ba lợi ích: xoá theo
thời hạn lưu trữ chỉ cần xoá tệp, trình duyệt tải nhanh vì tệp nhỏ, và mất điện giữa
chừng chỉ hỏng đoạn đang ghi.

Về codec: `avc1` (H.264) phát được trực tiếp trong thẻ <video> của trình duyệt, nhưng
bản OpenCV cài qua pip không phải lúc nào cũng kèm bộ mã hoá này. Lớp dưới đây thử
`avc1` trước, nếu thất bại thì lùi về `mp4v` và ghi nhận lại để hiển thị cảnh báo.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import cv2

from . import config, db

_FALLBACK_NOTIFIED = False


def _open_writer(path: Path, fps: float, size: tuple[int, int]):
    """Mở VideoWriter, ưu tiên H.264, tự lùi về mp4v nếu không khả dụng."""
    global _FALLBACK_NOTIFIED
    for fourcc_name in (config.RECORD_FOURCC, "mp4v"):
        writer = cv2.VideoWriter(
            str(path), cv2.VideoWriter_fourcc(*fourcc_name), fps, size
        )
        if writer.isOpened():
            if fourcc_name != config.RECORD_FOURCC and not _FALLBACK_NOTIFIED:
                _FALLBACK_NOTIFIED = True
                db.log(
                    f"Không mở được codec {config.RECORD_FOURCC}, dùng mp4v. "
                    "Trình duyệt có thể không phát trực tiếp được đoạn ghi; "
                    "cài OpenCV có H.264 hoặc chuyển mã bằng ffmpeg.",
                    level="warning",
                    source="recorder",
                )
            return writer, fourcc_name
        writer.release()
    return None, None


class SegmentRecorder:
    """Ghi khung hình vào các đoạn video nối tiếp nhau cho một camera."""

    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self.writer = None
        self.segment_id: str | None = None
        self.segment_path: Path | None = None
        self.segment_rel: str | None = None
        self.started_at: float = 0.0
        self.size: tuple[int, int] | None = None
        self.last_write: float = 0.0
        self.frame_interval = 1.0 / max(1.0, config.RECORD_FPS)

    # ── vòng đời một đoạn ────────────────────────────────────────────────────
    def _start_segment(self, frame) -> None:
        h, w = frame.shape[:2]
        scale = min(1.0, config.RECORD_MAX_WIDTH / max(1, w))
        # Kích thước phải chẵn, nhiều bộ mã hoá H.264 từ chối cạnh lẻ.
        size = (int(w * scale) // 2 * 2, int(h * scale) // 2 * 2)

        now = datetime.now()
        day_dir = config.SEGMENT_DIR / self.camera_id / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        seg_id = db.new_id()
        filename = f"{now.strftime('%H%M%S')}_{seg_id}.mp4"
        path = day_dir / filename

        writer, _ = _open_writer(path, config.RECORD_FPS, size)
        if writer is None:
            db.log(f"Không mở được tệp ghi hình {path}", level="error", source="recorder")
            return

        self.writer = writer
        self.size = size
        self.segment_id = seg_id
        self.segment_path = path
        self.segment_rel = str(path.relative_to(config.SEGMENT_DIR))
        self.started_at = time.time()

        db.execute(
            "INSERT INTO segments (id, camera_id, start_ts, path, duration) "
            "VALUES (?,?,?,?,?)",
            (seg_id, self.camera_id, db.now(), self.segment_rel, 0),
        )

    def _close_segment(self) -> None:
        if self.writer is None:
            return
        self.writer.release()
        duration = time.time() - self.started_at
        # Đoạn quá ngắn (dưới 1s) thường do camera vừa mất kết nối -> bỏ luôn.
        if duration < 1.0 and self.segment_path and self.segment_path.exists():
            self.segment_path.unlink(missing_ok=True)
            db.execute("DELETE FROM segments WHERE id=?", (self.segment_id,))
        else:
            db.execute(
                "UPDATE segments SET end_ts=?, duration=? WHERE id=?",
                (db.now(), round(duration, 2), self.segment_id),
            )
        self.writer = None
        self.segment_id = None
        self.segment_path = None

    # ── API ──────────────────────────────────────────────────────────────────
    def write(self, frame) -> None:
        """Ghi một khung hình, tự cắt đoạn mới khi đủ thời lượng."""
        now = time.time()
        # Giảm nhịp ghi xuống RECORD_FPS để tiết kiệm ổ đĩa.
        if now - self.last_write < self.frame_interval:
            return
        self.last_write = now

        if self.writer is not None and now - self.started_at >= config.SEGMENT_SECONDS:
            self._close_segment()
        if self.writer is None:
            self._start_segment(frame)
        if self.writer is None or self.size is None:
            return

        if (frame.shape[1], frame.shape[0]) != self.size:
            frame = cv2.resize(frame, self.size)
        self.writer.write(frame)

    def stop(self) -> None:
        self._close_segment()
