"""Điểm vào ứng dụng FastAPI của VisionOS.

Chạy:  python run.py       (hoặc: uvicorn app.main:app --reload)
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db, manager
from .routers import admin, cameras, events, pipelines, playback

_retention_timer: threading.Timer | None = None


def _schedule_retention(interval_hours: int = 6) -> None:
    """Hẹn giờ dọn dữ liệu quá hạn theo chu kỳ."""
    global _retention_timer

    def task() -> None:
        try:
            db.purge_expired()
        except Exception as exc:
            db.log(f"Lỗi khi dọn dữ liệu: {exc}", level="error", source="retention")
        _schedule_retention(interval_hours)

    _retention_timer = threading.Timer(interval_hours * 3600, task)
    _retention_timer.daemon = True
    _retention_timer.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    db.seed_if_empty()
    db.purge_orphans()
    db.log("Khởi động backend VisionOS", source="system")
    manager.sync_from_db()
    _schedule_retention()
    yield
    if _retention_timer:
        _retention_timer.cancel()
    manager.shutdown()
    db.log("Dừng backend VisionOS", source="system")


app = FastAPI(
    title="VisionOS API",
    description=(
        "Backend giám sát camera bằng thị giác máy tính. "
        "Phạm vi: xem trực tiếp, nhận diện và đếm người ra vào, xem lại và tìm kiếm."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router)
app.include_router(pipelines.router)
app.include_router(events.router)
app.include_router(playback.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["system"])
def health():
    workers = manager.all_workers()
    return {
        "status": "ok",
        "device": config.device(),
        "cameras_running": sum(1 for w in workers.values() if w.is_alive()),
    }
