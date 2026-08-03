"""Quản lý vòng đời các luồng camera.

Giữ một sổ đăng ký `camera_id -> CameraWorker` và đồng bộ nó với dữ liệu trong CSDL.
Toàn bộ phần còn lại của ứng dụng chỉ nói chuyện với module này, không tự tạo luồng.
"""
from __future__ import annotations

import json
import threading

from . import db
from .worker import CameraWorker

_workers: dict[str, CameraWorker] = {}
_lock = threading.RLock()


def get(camera_id: str) -> CameraWorker | None:
    with _lock:
        return _workers.get(camera_id)


def all_workers() -> dict[str, CameraWorker]:
    with _lock:
        return dict(_workers)


def start_camera(camera: dict) -> CameraWorker:
    """Khởi động luồng cho một camera; nếu đang chạy thì trả về luồng hiện có."""
    with _lock:
        existing = _workers.get(camera["id"])
        if existing and existing.is_alive():
            return existing

        worker = CameraWorker(camera)
        _workers[camera["id"]] = worker
        worker.start()

        # Gắn lại mọi pipeline đang bật của camera sau khi luồng đã chạy.
        for pipeline in db.query(
            "SELECT * FROM pipelines WHERE camera_id=? AND active=1 ORDER BY created_at",
            (camera["id"],),
        ):
            worker.add_pipeline(pipeline)
        return worker


def stop_camera(camera_id: str) -> None:
    with _lock:
        worker = _workers.pop(camera_id, None)
    if worker:
        worker.stop()
        worker.join(timeout=5)
        db.log("Dừng luồng camera", source=f"camera:{camera_id}")


def restart_camera(camera_id: str) -> CameraWorker | None:
    camera = db.query_one("SELECT * FROM cameras WHERE id=?", (camera_id,))
    stop_camera(camera_id)
    if camera and camera["enabled"]:
        return start_camera(camera)
    return None


def attach_pipeline(pipeline: dict) -> bool:
    """Bật pipeline: đảm bảo camera đang chạy rồi gắn cấu hình vào luồng."""
    camera = db.query_one("SELECT * FROM cameras WHERE id=?", (pipeline["camera_id"],))
    if not camera:
        return False

    worker = get(camera["id"])
    if worker is None or not worker.is_alive():
        worker = start_camera(camera)

    # Một camera chạy được nhiều pipeline cùng lúc, ví dụ vừa đếm người qua cửa vừa
    # đếm xe trong bãi. Bật cái này không đụng gì tới những cái đang chạy.
    db.execute("UPDATE pipelines SET active=1 WHERE id=?", (pipeline["id"],))

    fresh = db.query_one("SELECT * FROM pipelines WHERE id=?", (pipeline["id"],))
    worker.add_pipeline(fresh)
    db.log(f"Bật pipeline '{pipeline['name']}'", source=f"camera:{camera['id']}")
    return True


def detach_pipeline(pipeline_id: str) -> None:
    pipeline = db.query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,))
    db.execute("UPDATE pipelines SET active=0 WHERE id=?", (pipeline_id,))
    if not pipeline:
        return
    worker = get(pipeline["camera_id"])
    if worker:
        # Chỉ gỡ đúng pipeline này, các pipeline khác trên cùng camera vẫn chạy tiếp.
        worker.remove_pipeline(pipeline_id)
    db.log(f"Tắt pipeline '{pipeline['name']}'", source=f"camera:{pipeline['camera_id']}")


def sync_from_db() -> None:
    """Khởi động luồng cho mọi camera đang bật. Gọi lúc ứng dụng khởi động."""
    for camera in db.query("SELECT * FROM cameras WHERE enabled=1"):
        start_camera(camera)


def shutdown() -> None:
    for camera_id in list(all_workers()):
        stop_camera(camera_id)


def probe(source: str, timeout: float = 5.0) -> dict:
    """Thử mở nguồn video để kiểm tra kết nối trước khi lưu camera."""
    import time

    import cv2

    from .worker import _parse_source

    started = time.time()
    cap = cv2.VideoCapture(_parse_source(source))
    try:
        if not cap.isOpened():
            return {"ok": False, "message": "Không mở được nguồn video"}
        ok, frame = cap.read()
        if not ok or frame is None:
            return {"ok": False, "message": "Mở được nguồn nhưng không đọc được khung hình"}
        return {
            "ok": True,
            "message": "Kết nối thành công",
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": round(cap.get(cv2.CAP_PROP_FPS) or 0, 1),
            "elapsed_ms": round((time.time() - started) * 1000),
        }
    finally:
        cap.release()
