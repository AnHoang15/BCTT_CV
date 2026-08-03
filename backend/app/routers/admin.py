"""API quản trị: cấu hình chung, nhật ký hệ thống, dung lượng lưu trữ."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, Query

from .. import config, db, manager
from ..schemas import SettingsUpdate

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _dir_size(path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


@router.get("/settings")
def get_settings():
    return db.get_settings()


@router.put("/settings")
def update_settings(payload: SettingsUpdate):
    for key, value in payload.model_dump(exclude_none=True).items():
        db.set_setting(key, int(value) if isinstance(value, bool) else value)
    db.log("Cập nhật cấu hình hệ thống", source="admin")
    return db.get_settings()


@router.get("/storage")
def storage_usage():
    """Dung lượng đang dùng và dung lượng còn trống của ổ đĩa chứa dữ liệu."""
    usage = shutil.disk_usage(config.DATA_DIR)
    segments = _dir_size(config.SEGMENT_DIR)
    snapshots = _dir_size(config.SNAPSHOT_DIR)
    db_size = config.DB_PATH.stat().st_size if config.DB_PATH.exists() else 0

    return {
        "segments_bytes": segments,
        "snapshots_bytes": snapshots,
        "database_bytes": db_size,
        "used_bytes": segments + snapshots + db_size,
        "disk_total_bytes": usage.total,
        "disk_free_bytes": usage.free,
        "disk_used_percent": round(usage.used / usage.total * 100, 1),
        "retention_days": int(db.get_settings().get("retention_days", 7)),
        "segment_count": db.query_one("SELECT COUNT(*) AS n FROM segments")["n"],
        "snapshot_count": db.query_one(
            "SELECT COUNT(*) AS n FROM events WHERE snapshot IS NOT NULL"
        )["n"],
    }


@router.post("/storage/purge")
def purge_storage():
    """Xoá ngay dữ liệu quá thời hạn lưu trữ."""
    return db.purge_expired()


@router.get("/logs")
def list_logs(
    level: str | None = None,
    source: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
):
    sql = ["SELECT * FROM logs WHERE 1=1"]
    params: list = []
    if level:
        sql.append("AND level = ?")
        params.append(level)
    if source:
        sql.append("AND source LIKE ?")
        params.append(f"%{source}%")
    sql.append("ORDER BY id DESC LIMIT ?")
    params.append(limit)
    return db.query(" ".join(sql), params)


@router.get("/system")
def system_info():
    """Thông tin môi trường chạy — hữu ích khi chụp ảnh minh hoạ cho báo cáo."""
    import platform
    import sys

    workers = manager.all_workers()
    try:
        import torch
        torch_version = torch.__version__
    except Exception:
        torch_version = "chưa cài"

    return {
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "torch": torch_version,
        "device": config.device(),
        "yolo_weights": config.YOLO_WEIGHTS,
        "yolo_imgsz": config.YOLO_IMGSZ,
        "workers_running": sum(1 for w in workers.values() if w.is_alive()),
        "data_dir": str(config.DATA_DIR),
        "record_enabled": config.RECORD_ENABLED,
        "segment_seconds": config.SEGMENT_SECONDS,
    }
