"""Cấu hình tập trung cho backend VisionOS.

Mọi tham số đọc từ biến môi trường, có mặc định chạy được ngay không cần cấu hình.
"""
from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
DATA_DIR = Path(os.getenv("VISIONOS_DATA", BASE_DIR / "data"))

DB_PATH      = DATA_DIR / "visionos.db"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
SEGMENT_DIR  = DATA_DIR / "segments"
EXPORT_DIR   = DATA_DIR / "exports"

for _d in (DATA_DIR, SNAPSHOT_DIR, SEGMENT_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Mô hình phát hiện ────────────────────────────────────────────────────────
# yolov8n = nhẹ nhất, chạy được trên CPU. Đổi sang yolov8s/m/l nếu có GPU.
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", "yolov8n.pt")
YOLO_IMGSZ   = int(os.getenv("YOLO_IMGSZ", "960"))
YOLO_CONF    = float(os.getenv("YOLO_CONF", "0.25"))
NMS_IOU      = float(os.getenv("NMS_IOU", "0.5"))
MIN_BOX_AREA = int(os.getenv("MIN_BOX_AREA", "300"))

# Lớp COCO hỗ trợ. Bài toán chính là đếm người; các lớp phương tiện đi kèm miễn phí
# vì cùng một model COCO, không tốn thêm chi phí suy luận.
COCO_CLASSES: dict[str, int] = {
    "person": 0, "bicycle": 1, "car": 2, "motorcycle": 3,
    "bus": 5, "truck": 7,
}
CLASS_LABELS_VI: dict[str, str] = {
    "person": "Người", "bicycle": "Xe đạp", "car": "Ô tô",
    "motorcycle": "Xe máy", "bus": "Xe buýt", "truck": "Xe tải",
}

# ── Tracking (ByteTrack) ─────────────────────────────────────────────────────
# minimum_matching_threshold áp lên cost = 1 - IoU. Đặt 0.9 (tức chấp nhận IoU >= 0.1)
# thay vì mặc định 0.8, vì cảnh đông người box chồng lấn ít, ngưỡng gắt làm track
# chết sau 1 frame và không đếm được. Xem mục "Thực nghiệm" trong báo cáo.
TRACK_ACTIVATION_THRESHOLD = float(os.getenv("TRACK_ACT", "0.20"))
LOST_TRACK_BUFFER          = int(os.getenv("LOST_BUFFER", "50"))
MIN_MATCHING_THRESHOLD     = float(os.getenv("MIN_MATCH", "0.9"))
MIN_CONSECUTIVE_FRAMES     = int(os.getenv("MIN_CONSEC", "1"))

# ── Bộ đếm qua vạch ──────────────────────────────────────────────────────────
COUNTER_HISTORY      = int(os.getenv("COUNTER_HISTORY", "10"))
COUNTER_COOLDOWN     = int(os.getenv("COUNTER_COOLDOWN", "20"))
COUNTER_RELINK_DIST  = int(os.getenv("COUNTER_RELINK_DIST", "80"))
COUNTER_MARGIN_FRAC  = float(os.getenv("COUNTER_MARGIN", "0.03"))
COUNTER_DEBOUNCE     = int(os.getenv("COUNTER_DEBOUNCE", "3"))

# ── Luồng video ──────────────────────────────────────────────────────────────
STREAM_JPEG_QUALITY = int(os.getenv("STREAM_QUALITY", "75"))
STREAM_MAX_WIDTH    = int(os.getenv("STREAM_MAX_WIDTH", "960"))
TARGET_FPS          = float(os.getenv("TARGET_FPS", "15"))
RECONNECT_DELAY_S   = float(os.getenv("RECONNECT_DELAY", "3"))
# Trần cho việc giãn dần thời gian thử kết nối lại. Nguồn hỏng hẳn — webcam chưa cắm,
# camera IP mất điện — thì thử lại mỗi ba giây chỉ tốn CPU và làm bẩn nhật ký.
RECONNECT_MAX_DELAY_S = float(os.getenv("RECONNECT_MAX_DELAY", "60"))
# Khoảng nghỉ giữa hai cảnh báo vượt ngưỡng: đám đông đứng yên không nên sinh ra một
# cảnh báo mỗi khung hình.
OVERFLOW_COOLDOWN_SECONDS = float(os.getenv("OVERFLOW_COOLDOWN", "60"))
LABEL_HIDE_ABOVE    = int(os.getenv("LABEL_HIDE_ABOVE", "25"))

# ── Ghi hình phục vụ xem lại ─────────────────────────────────────────────────
RECORD_ENABLED     = os.getenv("RECORD_ENABLED", "1") == "1"
SEGMENT_SECONDS    = int(os.getenv("SEGMENT_SECONDS", "60"))
RECORD_FPS         = float(os.getenv("RECORD_FPS", "10"))
RECORD_MAX_WIDTH   = int(os.getenv("RECORD_MAX_WIDTH", "854"))
# avc1 (H.264) phát được trực tiếp trên trình duyệt. Bản OpenCV cài từ pip đôi khi
# thiếu codec này -> tự động lùi về mp4v (xem recorder.py).
RECORD_FOURCC      = os.getenv("RECORD_FOURCC", "avc1")

# ── Lưu trữ ──────────────────────────────────────────────────────────────────
DEFAULT_RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))
COUNT_SNAPSHOT_SECONDS = int(os.getenv("COUNT_SNAPSHOT_SECONDS", "60"))

# ── Luồng Thông minh: LocateAnything-3B ──────────────────────────────────────
# Mô hình nặng khoảng 7,3 GB nên không đóng gói kèm dự án. Trỏ biến môi trường
# LA3B_MODEL_DIR tới thư mục đã tải về, hoặc đặt vào backend/models/LocateAnything-3B.
LA3B_MODEL_DIR = os.getenv("LA3B_MODEL_DIR", str(BASE_DIR / "models" / "LocateAnything-3B"))
LA_CROP_SIZE = int(os.getenv("LA_CROP_SIZE", "160"))
LA_TEMPERATURE = float(os.getenv("LA_TEMPERATURE", "0.15"))
LA_VOTES = int(os.getenv("LA_VOTES", "1"))
LA_BATCH_SIZE = int(os.getenv("LA_BATCH_SIZE", "4"))
# Luồng Thông minh giữ vết lâu hơn: mỗi lần đổi mã định danh là một lần phải hỏi lại
# LA-3B, mà mỗi lần hỏi tốn khoảng một giây.
TM_LOST_TRACK_BUFFER = int(os.getenv("TM_LOST_BUFFER", "60"))
TM_MIN_MATCHING_THRESHOLD = float(os.getenv("TM_MIN_MATCH", "0.7"))

# ── HTTP ─────────────────────────────────────────────────────────────────────
API_HOST     = os.getenv("API_HOST", "0.0.0.0")
API_PORT     = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")


def device() -> str:
    """Chọn thiết bị suy luận: CUDA > MPS (Apple Silicon) > CPU."""
    forced = os.getenv("VISIONOS_DEVICE")
    if forced:
        return forced
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


# Backend MPS của PyTorch không an toàn khi nhiều luồng cùng gọi: hai luồng cùng dựng
# lệnh Metal sẽ đạp lên nhau trong tầng Objective-C và tiến trình chết ngay bằng SIGSEGV
# tại `min_max_out_mps`, không có ngoại lệ Python nào để bắt. Trước đây YOLO và LA-3B mỗi
# bên giữ một khoá riêng nên vẫn chạy song song được — chỉ cần bật một pipeline Thông
# minh là backend sập trong khoảng một phút.
#
# Mọi lời gọi suy luận, bất kể mô hình nào, phải đi qua đúng khoá này. Trên CUDA và CPU
# thì không cần, nên chỉ khoá thật khi đang chạy MPS.
_INFERENCE_LOCK = threading.Lock()


@contextlib.contextmanager
def inference_guard():
    """Nối tiếp các lần suy luận dùng chung một GPU Metal."""
    if device() == "mps":
        with _INFERENCE_LOCK:
            yield
    else:
        yield
