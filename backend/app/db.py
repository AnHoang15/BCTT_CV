"""Lớp truy cập SQLite.

Dùng `sqlite3` trực tiếp thay vì ORM: lược đồ nhỏ, truy vấn đơn giản, và quan trọng hơn
là dễ trình bày trong báo cáo. Một kết nối dùng chung cho toàn tiến trình, bảo vệ bằng
khoá vì các luồng xử lý camera cùng ghi vào đây.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Iterable

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    location    TEXT DEFAULT '',
    source      TEXT NOT NULL,           -- 0 | rtsp://... | /duong/dan/video.mp4
    kind        TEXT DEFAULT 'usb',      -- usb | rtsp | file
    enabled     INTEGER DEFAULT 1,
    retention_days INTEGER,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipelines (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    camera_id   TEXT NOT NULL,
    task        TEXT NOT NULL DEFAULT 'counting',   -- counting | detection
    mode        TEXT NOT NULL DEFAULT 'standard',   -- standard | smart
    prompt      TEXT,                               -- mô tả tiếng Việt cho luồng Thông minh
    classes     TEXT NOT NULL DEFAULT '["person"]', -- JSON list tên lớp COCO
    line        TEXT,                               -- JSON {x1,y1,x2,y2} toạ độ chuẩn hoá 0..1
    zone        TEXT,                               -- JSON [{x,y},...] đa giác chuẩn hoá 0..1
    flip        INTEGER DEFAULT 0,
    conf        REAL,                               -- ngưỡng tin cậy, để trống = dùng mặc định
    direction   TEXT DEFAULT 'both',                -- in | out | both
    max_count   INTEGER,                            -- cảnh báo khi vượt ngưỡng, NULL = tắt
    auto_reset  TEXT DEFAULT 'never',               -- never | hourly | daily
    target_fps  REAL,                               -- nhịp xử lý riêng, để trống = dùng mặc định
    schedule    TEXT,                               -- JSON {enabled, slots:[{days:[2..8], from, to}]}
    active      INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    camera_id   TEXT,
    pipeline_id TEXT,
    type        TEXT NOT NULL,          -- crossing | camera_offline | camera_online
    direction   TEXT,                   -- in | out
    label       TEXT,
    track_id    INTEGER,
    snapshot    TEXT,
    message     TEXT,
    status      TEXT DEFAULT 'new',     -- new | processing | closed
    note        TEXT,
    handled_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts     ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_camera ON events(camera_id, ts);

CREATE TABLE IF NOT EXISTS counts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    camera_id   TEXT,
    pipeline_id TEXT,
    in_total    INTEGER DEFAULT 0,
    out_total   INTEGER DEFAULT 0,
    in_delta    INTEGER DEFAULT 0,
    out_delta   INTEGER DEFAULT 0,
    occupancy   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_counts_ts ON counts(pipeline_id, ts);

CREATE TABLE IF NOT EXISTS segments (
    id          TEXT PRIMARY KEY,
    camera_id   TEXT NOT NULL,
    start_ts    TEXT NOT NULL,
    end_ts      TEXT,
    path        TEXT NOT NULL,
    duration    REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_segments ON segments(camera_id, start_ts);

CREATE TABLE IF NOT EXISTS logs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    level   TEXT DEFAULT 'info',
    source  TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _conn.executescript(SCHEMA)
            _migrate(_conn)
            _conn.commit()
        return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bổ sung cột mới cho cơ sở dữ liệu đã tạo từ phiên bản trước.

    `CREATE TABLE IF NOT EXISTS` không đụng tới bảng đã tồn tại, nên cột thêm sau phải
    tự thêm bằng ALTER TABLE.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(pipelines)")}
    for column, ddl in (
        ("mode", "ALTER TABLE pipelines ADD COLUMN mode TEXT NOT NULL DEFAULT 'standard'"),
        ("prompt", "ALTER TABLE pipelines ADD COLUMN prompt TEXT"),
        ("zone", "ALTER TABLE pipelines ADD COLUMN zone TEXT"),
        ("direction", "ALTER TABLE pipelines ADD COLUMN direction TEXT DEFAULT 'both'"),
        ("max_count", "ALTER TABLE pipelines ADD COLUMN max_count INTEGER"),
        ("auto_reset", "ALTER TABLE pipelines ADD COLUMN auto_reset TEXT DEFAULT 'never'"),
        ("target_fps", "ALTER TABLE pipelines ADD COLUMN target_fps REAL"),
        ("schedule", "ALTER TABLE pipelines ADD COLUMN schedule TEXT"),
    ):
        if column not in existing:
            conn.execute(ddl)


def query(sql: str, params: Iterable = ()) -> list[dict]:
    with _lock:
        cur = connect().execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Iterable = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable = ()) -> None:
    with _lock:
        conn = connect()
        conn.execute(sql, tuple(params))
        conn.commit()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log(message: str, level: str = "info", source: str = "system") -> None:
    execute(
        "INSERT INTO logs (ts, level, source, message) VALUES (?,?,?,?)",
        (now(), level, source, message),
    )


# ── Cấu hình hệ thống dạng key-value ─────────────────────────────────────────
DEFAULT_SETTINGS = {
    "retention_days": str(config.DEFAULT_RETENTION_DAYS),
    "record_enabled": "1" if config.RECORD_ENABLED else "0",
    "yolo_conf": str(config.YOLO_CONF),
    "target_fps": str(config.TARGET_FPS),
}


def get_settings() -> dict[str, str]:
    rows = query("SELECT key, value FROM settings")
    values = dict(DEFAULT_SETTINGS)
    values.update({r["key"]: r["value"] for r in rows})
    return values


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


# ── Ghi sự kiện / số đếm ─────────────────────────────────────────────────────
def insert_event(**kw) -> str:
    event_id = kw.pop("id", None) or new_id()
    fields = {
        "id": event_id,
        "ts": kw.get("ts") or now(),
        "camera_id": kw.get("camera_id"),
        "pipeline_id": kw.get("pipeline_id"),
        "type": kw.get("type", "crossing"),
        "direction": kw.get("direction"),
        "label": kw.get("label"),
        "track_id": kw.get("track_id"),
        "snapshot": kw.get("snapshot"),
        "message": kw.get("message"),
        "status": kw.get("status", "new"),
    }
    cols = ",".join(fields)
    marks = ",".join("?" * len(fields))
    execute(f"INSERT INTO events ({cols}) VALUES ({marks})", tuple(fields.values()))
    return event_id


def insert_count(camera_id, pipeline_id, in_total, out_total,
                 in_delta, out_delta, occupancy) -> None:
    execute(
        "INSERT INTO counts (ts, camera_id, pipeline_id, in_total, out_total, "
        "in_delta, out_delta, occupancy) VALUES (?,?,?,?,?,?,?,?)",
        (now(), camera_id, pipeline_id, in_total, out_total,
         in_delta, out_delta, occupancy),
    )


def _remove_snapshot(name: str) -> int:
    """Xoá một ảnh chụp cùng mọi bản thu nhỏ của nó. Trả về số tệp đã xoá."""
    removed = 0
    path = config.SNAPSHOT_DIR / name
    if path.exists():
        path.unlink(missing_ok=True)
        removed += 1
    thumbs = config.SNAPSHOT_DIR / "thumbs"
    if thumbs.is_dir():
        for thumb in thumbs.glob(f"{path.stem}_*.jpg"):
            thumb.unlink(missing_ok=True)
            removed += 1
    return removed


def purge_camera_data(camera_id: str) -> dict[str, int]:
    """Xoá mọi dữ liệu phát sinh của một camera: đoạn ghi hình, ảnh chụp, sự kiện, số đếm.

    Gọi trước khi xoá bản ghi camera. Không dựa vào khoá ngoại vì `segments` và `events`
    còn giữ tệp trên đĩa, xoá dòng trong bảng không đủ.
    """
    removed = 0
    for row in query("SELECT path FROM segments WHERE camera_id=?", (camera_id,)):
        path = config.SEGMENT_DIR / row["path"]
        if path.exists():
            path.unlink(missing_ok=True)
            removed += 1
    # Dọn luôn thư mục rỗng còn sót lại của camera.
    cam_dir = config.SEGMENT_DIR / camera_id
    if cam_dir.exists():
        for day_dir in sorted(cam_dir.glob("*"), reverse=True):
            if day_dir.is_dir() and not any(day_dir.iterdir()):
                day_dir.rmdir()
        if not any(cam_dir.iterdir()):
            cam_dir.rmdir()

    for row in query(
        "SELECT snapshot FROM events WHERE camera_id=? AND snapshot IS NOT NULL",
        (camera_id,),
    ):
        removed += _remove_snapshot(row["snapshot"])

    execute("DELETE FROM segments WHERE camera_id=?", (camera_id,))
    execute("DELETE FROM events   WHERE camera_id=?", (camera_id,))
    execute("DELETE FROM counts   WHERE camera_id=?", (camera_id,))
    return {"files": removed}


def purge_orphans() -> dict[str, int]:
    """Dọn bản ghi trỏ tới camera không còn tồn tại.

    Cần thiết vì các bản cài đặt trước chưa dọn theo camera khi xoá, để lại đoạn ghi
    hình mồ côi hiển thị nhầm ở trang Xem lại.
    """
    alive = {r["id"] for r in query("SELECT id FROM cameras")}
    removed = 0
    for table in ("segments", "events", "counts"):
        rows = query(f"SELECT DISTINCT camera_id FROM {table}")
        for row in rows:
            cam = row["camera_id"]
            if cam and cam not in alive:
                removed += purge_camera_data(cam)["files"]
                execute(f"DELETE FROM {table} WHERE camera_id=?", (cam,))
    if removed:
        log(f"Dọn {removed} tệp mồ côi của camera đã xoá", source="maintenance")
    return {"files": removed}


# ── Dọn dữ liệu quá hạn ──────────────────────────────────────────────────────
def purge_expired() -> dict[str, int]:
    """Xoá bản ghi và tệp cũ hơn thời hạn lưu trữ. Trả về số lượng đã xoá."""
    days = int(get_settings().get("retention_days", config.DEFAULT_RETENTION_DAYS))
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")

    removed_files = 0
    for row in query("SELECT id, path FROM segments WHERE start_ts < ?", (cutoff,)):
        path = config.SEGMENT_DIR / row["path"]
        if path.exists():
            path.unlink(missing_ok=True)
            removed_files += 1
    execute("DELETE FROM segments WHERE start_ts < ?", (cutoff,))

    for row in query(
        "SELECT snapshot FROM events WHERE ts < ? AND snapshot IS NOT NULL", (cutoff,)
    ):
        removed_files += _remove_snapshot(row["snapshot"])
    execute("DELETE FROM events WHERE ts < ?", (cutoff,))
    execute("DELETE FROM counts WHERE ts < ?", (cutoff,))
    execute("DELETE FROM logs  WHERE ts < ?", (cutoff,))

    log(f"Dọn dữ liệu quá {days} ngày: xoá {removed_files} tệp", source="retention")
    return {"files": removed_files, "cutoff": cutoff}


# ── Dữ liệu mẫu khi khởi tạo lần đầu ─────────────────────────────────────────
def seed_if_empty() -> None:
    if query_one("SELECT id FROM cameras LIMIT 1"):
        return
    # Tạo ở trạng thái TẮT: người dùng tự bật để tránh hệ điều hành bật webcam và
    # hỏi quyền truy cập ngay lần chạy đầu tiên.
    cam_id = new_id()
    execute(
        "INSERT INTO cameras (id, name, location, source, kind, enabled, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (cam_id, "Webcam nội bộ", "Phòng thực tập", "0", "usb", 0, now()),
    )
    execute(
        "INSERT INTO pipelines (id, name, camera_id, task, classes, line, flip, "
        "conf, active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            new_id(), "Đếm người ra vào cửa", cam_id, "counting",
            json.dumps(["person"]),
            json.dumps({"x1": 0.0, "y1": 0.55, "x2": 1.0, "y2": 0.55}),
            0, config.YOLO_CONF, 0, now(),
        ),
    )
    log("Khởi tạo dữ liệu mẫu", source="setup")
