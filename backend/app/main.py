"""Điểm vào ứng dụng FastAPI của VisionOS.

Chạy:  python run.py       (hoặc: uvicorn app.main:app --reload)
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db, manager
from .routers import admin, ai, cameras, events, pipelines, playback

_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

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
    db.purge_expired()  # dọn ngay lúc khởi động, không chờ chu kỳ 6 giờ
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
app.include_router(ai.router)


@app.get("/api/health", tags=["system"])
def health():
    workers = manager.all_workers()
    return {
        "status": "ok",
        "device": config.device(),
        "cameras_running": sum(1 for w in workers.values() if w.is_alive()),
    }


# ── Phục vụ frontend đã build ────────────────────────────────────────────────
if _FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIR / "assets")), name="static-assets")

    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Catch-all: trả index.html cho mọi route không phải /api.

        Không cho cache index.html (không có header cache), nếu không trình duyệt sẽ
        giữ bản cũ và tải bundle JS đã cũ sau mỗi lần build frontend.
        """
        index = _FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index), headers={"Cache-Control": "no-cache"})
        return {"detail": "Frontend not built"}
