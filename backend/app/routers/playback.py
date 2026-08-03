"""API xem lại: liệt kê các đoạn ghi hình, dựng dòng thời gian và phát video."""
from __future__ import annotations

import mimetypes
import re
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from .. import config, db

router = APIRouter(prefix="/api/playback", tags=["playback"])

CHUNK_SIZE = 1024 * 1024


def _serve_with_range(path: Path, request: Request) -> Response:
    """Phục vụ tệp video có hỗ trợ HTTP Range.

    Bắt buộc phải có Range thì thẻ <video> mới tua được: không có nó trình duyệt phải
    tải hết tệp mới phát và thanh tua bị vô hiệu.
    """
    file_size = path.stat().st_size
    media_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)},
        )

    match = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not match:
        raise HTTPException(416, "Range không hợp lệ")

    start_raw, end_raw = match.groups()
    start = int(start_raw) if start_raw else 0
    end = int(end_raw) if end_raw else min(start + CHUNK_SIZE - 1, file_size - 1)
    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        return Response(
            status_code=416, headers={"Content-Range": f"bytes */{file_size}"}
        )

    def iter_chunk():
        remaining = end - start + 1
        with path.open("rb") as fh:
            fh.seek(start)
            while remaining > 0:
                data = fh.read(min(CHUNK_SIZE, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(
        iter_chunk(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
        },
    )


@router.get("/segments")
def list_segments(
    camera_id: str = Query(...),
    date: str | None = Query(None, description="YYYY-MM-DD, mặc định hôm nay"),
):
    """Các đoạn ghi hình của một camera trong một ngày."""
    day = date or datetime.now().strftime("%Y-%m-%d")
    try:
        start = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, "Định dạng ngày phải là YYYY-MM-DD")
    end = start + timedelta(days=1)

    rows = db.query(
        "SELECT * FROM segments WHERE camera_id=? AND start_ts >= ? AND start_ts < ? "
        "ORDER BY start_ts",
        (camera_id, start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
    )

    segments = []
    for row in rows:
        exists = (config.SEGMENT_DIR / row["path"]).exists()
        started = datetime.fromisoformat(row["start_ts"])
        segments.append({
            **row,
            "available": exists,
            "clock": started.strftime("%H:%M:%S"),
            # Vị trí trong ngày tính theo giây — frontend dùng để đặt điểm trên timeline.
            "offset_seconds": (started - start).total_seconds(),
        })
    return {"date": day, "count": len(segments), "segments": segments}


@router.get("/dates")
def list_dates(camera_id: str = Query(...)):
    """Những ngày có dữ liệu ghi hình, để đánh dấu trên bộ chọn ngày."""
    rows = db.query(
        "SELECT DISTINCT substr(start_ts, 1, 10) AS day FROM segments "
        "WHERE camera_id=? ORDER BY day DESC LIMIT 60",
        (camera_id,),
    )
    return [r["day"] for r in rows]


@router.get("/timeline")
def timeline(
    camera_id: str = Query(...),
    date: str | None = None,
):
    """Gộp đoạn ghi hình và sự kiện của một ngày thành dữ liệu cho thanh thời gian."""
    day = date or datetime.now().strftime("%Y-%m-%d")
    try:
        start = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, "Định dạng ngày phải là YYYY-MM-DD")
    end = start + timedelta(days=1)

    events = db.query(
        "SELECT * FROM events WHERE camera_id=? AND ts >= ? AND ts < ? ORDER BY ts",
        (camera_id, start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
    )
    for event in events:
        moment = datetime.fromisoformat(event["ts"])
        event["offset_seconds"] = (moment - start).total_seconds()
        event["clock"] = moment.strftime("%H:%M:%S")

    return {
        "date": day,
        "segments": list_segments(camera_id, day)["segments"],
        "events": events,
    }


@router.get("/segments/{segment_id}/video")
def segment_video(segment_id: str, request: Request):
    row = db.query_one("SELECT * FROM segments WHERE id=?", (segment_id,))
    if not row:
        raise HTTPException(404, "Không tìm thấy đoạn ghi hình")
    path = config.SEGMENT_DIR / row["path"]
    if not path.exists():
        raise HTTPException(404, "Tệp đã bị xoá theo thời hạn lưu trữ")
    return _serve_with_range(path, request)


@router.get("/at")
def segment_at(camera_id: str, ts: str):
    """Tìm đoạn ghi hình chứa một mốc thời gian.

    Dùng khi người dùng bấm vào một sự kiện trong danh sách và muốn nhảy tới đúng vị trí
    đó trong video. Trả về đoạn kèm số giây cần tua bên trong đoạn.
    """
    try:
        moment = datetime.fromisoformat(ts)
    except ValueError:
        raise HTTPException(422, "Mốc thời gian không hợp lệ")

    row = db.query_one(
        "SELECT * FROM segments WHERE camera_id=? AND start_ts <= ? "
        "ORDER BY start_ts DESC LIMIT 1",
        (camera_id, moment.isoformat(timespec="seconds")),
    )
    if not row:
        raise HTTPException(404, "Không có đoạn ghi hình nào trước mốc này")

    started = datetime.fromisoformat(row["start_ts"])
    seek = (moment - started).total_seconds()
    if row["duration"] and seek > row["duration"] + 5:
        raise HTTPException(404, "Mốc thời gian nằm ngoài đoạn ghi hình gần nhất")

    return {"segment": row, "seek_seconds": max(0.0, seek)}
