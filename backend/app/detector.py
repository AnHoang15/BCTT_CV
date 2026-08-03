"""Bộ phát hiện và bám vết đối tượng: YOLOv8 (Ultralytics) + ByteTrack (Supervision).

Model YOLO được nạp một lần và dùng chung cho mọi camera — nạp lại mỗi luồng sẽ tốn
gấp N lần bộ nhớ GPU mà không nhanh hơn. Mỗi camera giữ một tracker riêng vì trạng thái
bám vết là cục bộ theo từng luồng video.
"""
from __future__ import annotations

import threading

import numpy as np

from . import config

_model = None
_model_lock = threading.Lock()


def get_model():
    """Nạp YOLO theo kiểu lazy, chỉ một lần cho toàn tiến trình."""
    global _model
    with _model_lock:
        if _model is None:
            from ultralytics import YOLO

            _model = YOLO(config.YOLO_WEIGHTS)
            dev = config.device()
            try:
                _model.to(dev)
            except Exception:
                pass
            print(f"[detector] Đã nạp {config.YOLO_WEIGHTS} trên thiết bị {dev}")
        return _model


def new_tracker(fps: float = 30.0, smart: bool = False):
    """Tạo ByteTrack với tham số đã hiệu chỉnh cho cảnh đông người.

    `minimum_matching_threshold` áp lên chi phí `1 - IoU`. Giá trị mặc định quá gắt làm
    track chết ngay sau một khung hình ở cảnh đông, khiến không đối tượng nào tồn tại đủ
    lâu để vượt vạch. Xem phần thực nghiệm trong báo cáo.

    Luồng Thông minh dùng bộ tham số riêng, giữ vết lâu hơn: mỗi lần đổi mã định danh
    là một lần phải hỏi lại LA-3B, mà mỗi lần hỏi tốn khoảng một giây.
    """
    import supervision as sv

    kwargs = {
        "frame_rate": max(1, int(fps)),
        "track_activation_threshold": config.TRACK_ACTIVATION_THRESHOLD,
        "lost_track_buffer": (
            config.TM_LOST_TRACK_BUFFER if smart else config.LOST_TRACK_BUFFER
        ),
        "minimum_matching_threshold": (
            config.TM_MIN_MATCHING_THRESHOLD if smart else config.MIN_MATCHING_THRESHOLD
        ),
        "minimum_consecutive_frames": config.MIN_CONSECUTIVE_FRAMES,
    }
    try:
        return sv.ByteTrack(**kwargs)
    except TypeError:
        # Phiên bản supervision cũ dùng tên tham số khác -> dùng mặc định.
        return sv.ByteTrack()


def class_ids(class_names: list[str]) -> list[int]:
    return [config.COCO_CLASSES[c] for c in class_names if c in config.COCO_CLASSES]


def apply_nms(detections, iou_threshold: float = config.NMS_IOU):
    """Khử hộp trùng. IoU cao (0.5) để không gộp nhầm hai người đứng sát nhau."""
    if len(detections) == 0:
        return detections
    try:
        return detections.with_nms(threshold=iou_threshold)
    except Exception:
        return detections


def filter_min_size(detections, min_area: int = config.MIN_BOX_AREA):
    """Loại hộp quá nhỏ — thường là nhiễu nền hoặc phản chiếu."""
    if len(detections) == 0:
        return detections
    x1, y1, x2, y2 = detections.xyxy.T
    return detections[((x2 - x1) * (y2 - y1)) >= min_area]


class Detector:
    """Gói một luồng phát hiện + bám vết cho một camera."""

    def __init__(self, class_names: list[str], conf: float | None = None,
                 fps: float = 30.0, smart: bool = False) -> None:
        self.class_names = class_names or ["person"]
        self.class_ids = class_ids(self.class_names)
        self.conf = conf if conf is not None else config.YOLO_CONF
        self.smart = smart
        self.tracker = new_tracker(fps, smart)
        self._id_to_name = {v: k for k, v in config.COCO_CLASSES.items()}

    def reset_tracker(self, fps: float = 30.0) -> None:
        self.tracker = new_tracker(fps, self.smart)

    def __call__(self, frame: np.ndarray):
        """Phát hiện rồi bám vết trên một khung hình.

        Trả về (boxes Nx4, tracker_ids, labels, confidences).
        """
        return self.track(detect(frame, self.class_ids, self.conf))

    def track(self, detections):
        """Bám vết trên tập hộp đã phát hiện sẵn.

        Tách khỏi `__call__` để nhiều pipeline trên cùng một camera dùng chung đúng một
        lần gọi YOLO. Mỗi pipeline vẫn giữ tracker riêng vì mã định danh vết phải độc
        lập: hai pipeline đếm hai vạch khác nhau không được chia nhau trạng thái bám.

        Lọc lại theo lớp và ngưỡng tin cậy của riêng pipeline này, vì tập hộp truyền
        vào là hợp của mọi pipeline nên rộng hơn thứ pipeline này cần.
        """
        if len(detections):
            keep = detections.confidence >= self.conf if detections.confidence is not None \
                else np.ones(len(detections), dtype=bool)
            if self.class_ids and detections.class_id is not None:
                keep = keep & np.isin(detections.class_id, self.class_ids)
            detections = detections[keep]

        detections = self.tracker.update_with_detections(detections)

        if len(detections) == 0 or detections.tracker_id is None:
            return np.empty((0, 4)), [], [], []

        labels = [
            self._id_to_name.get(int(c), "object")
            for c in (detections.class_id if detections.class_id is not None
                      else np.zeros(len(detections), dtype=int))
        ]
        confs = (detections.confidence.tolist()
                 if detections.confidence is not None else [1.0] * len(detections))
        return detections.xyxy, [int(t) for t in detections.tracker_id], labels, confs


def detect(frame: np.ndarray, class_ids: list[int], conf: float):
    """Một lần gọi YOLO, trả về `sv.Detections` đã khử trùng và bỏ hộp quá nhỏ.

    Không bám vết ở đây. Nhiều pipeline cùng camera gọi hàm này đúng một lần với hợp
    các lớp và ngưỡng tin cậy thấp nhất, rồi mỗi pipeline tự lọc và tự bám vết.
    """
    import supervision as sv

    model = get_model()
    # Ultralytics không đảm bảo an toàn khi nhiều luồng cùng gọi predict, và trên
    # Apple Silicon còn phải tránh đụng độ với LA-3B — cả hai dùng chung khoá này.
    with config.inference_guard():
        result = model(
            frame,
            classes=class_ids or None,
            conf=conf,
            imgsz=config.YOLO_IMGSZ,
            verbose=False,
        )[0]

    return filter_min_size(apply_nms(sv.Detections.from_ultralytics(result)))
