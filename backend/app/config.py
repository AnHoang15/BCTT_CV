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
# Ba tham số dưới đây đã đo trên nhãn chuẩn MOT17 (`scripts/danh_gia_mot17.py`), và
# kết quả đi ngược trực giác: phát hiện được nhiều người hơn KHÔNG làm số đếm đúng hơn.
# Người ở xa, nhỏ, bị che phần lớn không đi qua vạch, nhưng lại làm bộ bám vết phải
# ghép thêm nhiều hộp yếu, sinh vết vỡ và mã vết trôi — nguồn gốc của lượt đếm giả.
# Chỉ số cần tối ưu là "thấy đúng người đang bước qua vạch", không phải "thấy được bao
# nhiêu người trong khung".
#
#   trọng số   yolov8n 0,91 · yolo11n 0,91 · yolo12n 0,88 · yolo11s 0,88  (F1 đếm)
#   imgsz      640 0,86 · 960 0,91 · 1280 0,86 · 1536 0,86
#   conf       0,25 và 0,35 cho kết quả BẰNG NHAU (F1 gộp 0,81 trên 18 cấu hình)
#
# Ba giá trị hiện tại đều là mặc định từ đầu dự án, và cả ba đều đã được kiểm chứng là
# không có lựa chọn nào tốt hơn rõ rệt.
#
# yolov8n = nhẹ nhất, chạy được trên CPU. Đổi sang yolov8s/m/l nếu có GPU.
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", "yolov8n.pt")
YOLO_IMGSZ   = int(os.getenv("YOLO_IMGSZ", "960"))

# Từng đổi lên 0,35 rồi trả về 0,25. Một phép đo trung gian cho thấy 0,35 loại được một
# lượt đếm giả, nhưng phép đo ấy chạy trên đường ống rút gọn (gọi thẳng YOLO + ByteTrack)
# chứ không qua lớp `Detector` — mà lớp đó còn khử trùng lặp NMS và lọc hộp dưới
# MIN_BOX_AREA, tức đã loại sẵn phần lớn hộp yếu ở xa. Nâng ngưỡng chỉ lặp lại việc đã
# làm rồi. Đo lại qua đường ống thật: hai ngưỡng bằng nhau, và ở một vị trí vạch thì
# 0,35 còn kém hơn (0,93 so với 1,00).
#
# Bài học: đo tham số phải chạy đúng đường ống của hệ thống, không phải bản rút gọn.
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
# Vùng đệm quanh vạch, tính theo chiều cao hộp đối tượng (0.03 = 3% chiều cao người).
# Không còn tính theo độ dài vạch, và hệ số đã hiệu chỉnh theo các lượt qua vạch xác
# minh bằng mắt — xem chú thích trong counter.py.
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
# Mỗi sự kiện vượt vạch lưu một ảnh chụp đầy đủ cỡ khung hình (có camera 4K ->
# ~550KB/snapshot) nên đĩa đầy rất nhanh. Giữ lại dữ liệu ngắn (3 ngày) và thu
# nhỏ ảnh chụp xuống 320px — hai thứ này quyết định gần như toàn bộ dung lượng.
DEFAULT_RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "3"))
# Chiều rộng tối đa (px) của ảnh chụp sự kiện; giữ tỷ lệ khung hình gốc.
SNAPSHOT_MAX_WIDTH = int(os.getenv("SNAPSHOT_MAX_WIDTH", "320"))
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
