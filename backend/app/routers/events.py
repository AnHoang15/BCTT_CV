"""API sự kiện, số đếm theo thời gian và tìm kiếm bằng tiếng Việt."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

import cv2
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from .. import config, db, search
from ..schemas import EventUpdate

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
def list_events(
    camera_id: str | None = None,
    pipeline_id: str | None = None,
    type: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    sql = [
        "SELECT e.*, c.name AS camera_name FROM events e",
        "LEFT JOIN cameras c ON c.id = e.camera_id WHERE 1=1",
    ]
    params: list = []
    for column, value in (
        ("e.camera_id", camera_id), ("e.pipeline_id", pipeline_id),
        ("e.type", type), ("e.direction", direction), ("e.status", status),
    ):
        if value:
            sql.append(f"AND {column} = ?")
            params.append(value)
    if date_from:
        sql.append("AND e.ts >= ?")
        params.append(date_from)
    if date_to:
        sql.append("AND e.ts <= ?")
        params.append(date_to)

    sql.append("ORDER BY e.ts DESC LIMIT ?")
    params.append(limit)
    return db.query(" ".join(sql), params)


@router.patch("/events/{event_id}")
def update_event(event_id: str, payload: EventUpdate):
    """Xác nhận xử lý (ACK) hoặc đóng sự kiện kèm ghi chú."""
    if not db.query_one("SELECT id FROM events WHERE id=?", (event_id,)):
        raise HTTPException(404, "Không tìm thấy sự kiện")

    fields = payload.model_dump(exclude_none=True)
    if fields.get("status") in ("processing", "closed"):
        fields["handled_at"] = db.now()
    if fields:
        assignments = ", ".join(f"{k}=?" for k in fields)
        db.execute(
            f"UPDATE events SET {assignments} WHERE id=?", (*fields.values(), event_id)
        )
    return db.query_one("SELECT * FROM events WHERE id=?", (event_id,))


@router.get("/events/{event_id}/snapshot")
def event_snapshot(event_id: str, w: int = Query(0, ge=0, le=3840)):
    """Ảnh chụp của sự kiện. Truyền `w` để lấy bản thu nhỏ theo chiều rộng.

    Cần thiết vì ảnh gốc chụp từ camera 4K nặng khoảng nửa megabyte; một lưới 80 kết
    quả tìm kiếm sẽ phải tải hàng chục megabyte nếu lần nào cũng trả ảnh gốc. Bản thu
    nhỏ được sinh một lần rồi lưu lại để các lần sau đọc thẳng từ đĩa.
    """
    row = db.query_one("SELECT snapshot FROM events WHERE id=?", (event_id,))
    if not row or not row["snapshot"]:
        raise HTTPException(404, "Sự kiện không có ảnh chụp")

    path = config.SNAPSHOT_DIR / row["snapshot"]
    if not path.exists():
        raise HTTPException(404, "Tệp ảnh đã bị xoá theo thời hạn lưu trữ")
    if not w:
        return FileResponse(path, media_type="image/jpeg")

    thumb = _thumbnail(path, w)
    return FileResponse(thumb or path, media_type="image/jpeg")


def _thumbnail(source: Path, width: int) -> Path | None:
    """Sinh (hoặc lấy lại) bản thu nhỏ. Trả về None nếu không tạo được."""
    cache_dir = config.SNAPSHOT_DIR / "thumbs"
    target = cache_dir / f"{source.stem}_{width}.jpg"
    if target.exists():
        return target

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        image = cv2.imread(str(source))
        if image is None:
            return None
        height = max(1, round(image.shape[0] * width / image.shape[1]))
        resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(target), resized, [cv2.IMWRITE_JPEG_QUALITY, 78])
        return target
    except Exception:
        return None


@router.get("/search")
def natural_language_search(q: str = Query(..., min_length=1), limit: int = 200):
    """Tìm sự kiện bằng câu tiếng Việt, ví dụ: 'người đi vào hôm qua buổi sáng'."""
    return search.search_events(q, limit)


@router.get("/counts")
def counts_series(
    pipeline_id: str | None = None,
    camera_id: str | None = None,
    hours: int = Query(24, ge=1, le=720),
):
    """Chuỗi số đếm theo giờ, dùng để vẽ biểu đồ lưu lượng.

    Gộp trực tiếp từ bảng `events` thay vì bảng `counts` để mỗi khung giờ phản ánh đúng
    số lượt phát sinh trong giờ đó, không bị ảnh hưởng bởi thời điểm ghi mốc.
    """
    since = (datetime.now() - timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0
    )

    sql = ["SELECT ts, direction FROM events WHERE type='crossing' AND ts >= ?"]
    params: list = [since.isoformat(timespec="seconds")]
    if pipeline_id:
        sql.append("AND pipeline_id = ?")
        params.append(pipeline_id)
    if camera_id:
        sql.append("AND camera_id = ?")
        params.append(camera_id)

    rows = db.query(" ".join(sql), params)

    buckets: OrderedDict[str, dict] = OrderedDict()
    cursor = since
    now = datetime.now()
    while cursor <= now:
        buckets[cursor.strftime("%Y-%m-%d %H:00")] = {
            "bucket": cursor.strftime("%d/%m %Hh"),
            "key": cursor.strftime("%Y-%m-%d %H:00"),
            "in": 0,
            "out": 0,
        }
        cursor += timedelta(hours=1)

    for row in rows:
        try:
            key = datetime.fromisoformat(row["ts"]).strftime("%Y-%m-%d %H:00")
        except ValueError:
            continue
        if key in buckets:
            buckets[key]["in" if row["direction"] == "in" else "out"] += 1

    series = list(buckets.values())
    total_in = sum(b["in"] for b in series)
    total_out = sum(b["out"] for b in series)
    peak = max(series, key=lambda b: b["in"] + b["out"], default=None)

    return {
        "series": series,
        "total_in": total_in,
        "total_out": total_out,
        "net": total_in - total_out,
        "peak_bucket": peak["bucket"] if peak and (peak["in"] + peak["out"]) else None,
    }


@router.get("/summary")
def dashboard_summary():
    """Số liệu tổng hợp cho thanh trạng thái ở giao diện."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_iso = today.isoformat(timespec="seconds")

    cameras = db.query("SELECT enabled FROM cameras")
    events_today = db.query_one(
        "SELECT COUNT(*) AS n FROM events WHERE ts >= ?", (today_iso,)
    )
    crossings = db.query(
        "SELECT direction, COUNT(*) AS n FROM events "
        "WHERE type='crossing' AND ts >= ? GROUP BY direction",
        (today_iso,),
    )
    by_direction = {r["direction"]: r["n"] for r in crossings}
    unread = db.query_one("SELECT COUNT(*) AS n FROM events WHERE status='new'")

    return {
        "cameras_total": len(cameras),
        "cameras_enabled": sum(1 for c in cameras if c["enabled"]),
        "pipelines_active": db.query_one(
            "SELECT COUNT(*) AS n FROM pipelines WHERE active=1"
        )["n"],
        "events_today": events_today["n"],
        "in_today": by_direction.get("in", 0),
        "out_today": by_direction.get("out", 0),
        "unread_events": unread["n"],
    }
