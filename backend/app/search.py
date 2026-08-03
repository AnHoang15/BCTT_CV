"""Tìm kiếm sự kiện bằng câu tiếng Việt.

Cách tiếp cận là phân tích câu bằng luật thay vì gọi mô hình ngôn ngữ. Lý do: phạm vi
truy vấn của hệ thống hẹp và đóng (đối tượng nào, chiều nào, camera nào, khoảng thời
gian nào), nên một bộ luật vài chục dòng cho kết quả xác định, chạy offline, độ trễ
dưới một mili giây và giải thích được cho người dùng biết hệ thống đã hiểu câu ra sao.

Ví dụ: "người đi vào cửa chính hôm qua từ 8h đến 11h"
    -> {label: person, direction: in, camera: "cửa chính",
        from: hôm qua 08:00, to: hôm qua 11:00}
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

from . import db

# ── Từ điển ánh xạ ───────────────────────────────────────────────────────────
OBJECT_KEYWORDS: dict[str, list[str]] = {
    "person": ["nguoi", "khach", "nhan vien", "hoc sinh", "ai do"],
    "motorcycle": ["xe may", "mo to", "xe gan may"],
    "car": ["o to", "xe hoi", "xe con", "oto"],
    "truck": ["xe tai", "container"],
    "bus": ["xe buyt", "xe khach"],
    "bicycle": ["xe dap"],
}

DIRECTION_IN = ["di vao", "vao trong", "vao", "di vo", "entering", "enter"]
DIRECTION_OUT = ["di ra", "ra ngoai", "ra", "roi khoi", "exiting", "exit"]

STOPWORDS = {
    "tim", "kiem", "cho", "toi", "xem", "lai", "cac", "nhung", "co", "la", "va",
    "hay", "liet", "ke", "tat", "ca", "su", "kien", "camera", "luc", "khi", "nao",
    "bao", "nhieu", "may", "gio", "phut", "tu", "den", "khoang", "trong", "o", "tai",
}


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp không phụ thuộc cách gõ."""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


def _day_bounds(day: datetime) -> tuple[datetime, datetime]:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def parse_time_range(text: str) -> tuple[datetime | None, datetime | None, str | None]:
    """Rút khoảng thời gian từ câu. Trả về (từ, đến, mô tả đã hiểu)."""
    now = datetime.now()
    base_start = base_end = None
    described = None

    if "hom qua" in text:
        base_start, base_end = _day_bounds(now - timedelta(days=1))
        described = "hôm qua"
    elif "hom nay" in text or "hom nai" in text:
        base_start, base_end = _day_bounds(now)
        described = "hôm nay"
    elif "tuan nay" in text:
        monday = now - timedelta(days=now.weekday())
        base_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        base_end = base_start + timedelta(days=7)
        described = "tuần này"
    elif "tuan truoc" in text:
        monday = now - timedelta(days=now.weekday() + 7)
        base_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        base_end = base_start + timedelta(days=7)
        described = "tuần trước"
    else:
        m = re.search(r"(\d+)\s*ngay\s*(truoc|qua|gan day|vua qua)", text)
        if m:
            days = int(m.group(1))
            base_start = (now - timedelta(days=days)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            base_end = now
            described = f"{days} ngày gần đây"

    # Buổi trong ngày
    period = None
    if "sang" in text:
        period = (6, 12, "buổi sáng")
    elif "trua" in text:
        period = (11, 14, "buổi trưa")
    elif "chieu" in text:
        period = (12, 18, "buổi chiều")
    elif "toi" in text or "dem" in text:
        period = (18, 24, "buổi tối")

    # Khoảng giờ tường minh: "tu 8h den 11h", "8:00 - 11:30"
    hours = re.search(
        r"(\d{1,2})(?:[h:](\d{2})?)?\s*(?:gio)?\s*(?:-|den|toi|->)\s*(\d{1,2})(?:[h:](\d{2})?)?",
        text,
    )

    anchor = base_start or _day_bounds(now)[0]
    if hours:
        h1, m1, h2, m2 = hours.groups()
        start = anchor.replace(hour=int(h1) % 24, minute=int(m1 or 0),
                               second=0, microsecond=0)
        end = anchor.replace(hour=int(h2) % 24, minute=int(m2 or 0),
                             second=0, microsecond=0)
        if end <= start:
            end += timedelta(days=1)
        label = f"{described + ' ' if described else ''}{h1}h–{h2}h"
        return start, end, label.strip()

    if period and base_start:
        h1, h2, name = period
        start = anchor.replace(hour=h1, minute=0, second=0, microsecond=0)
        end = anchor.replace(hour=min(h2, 23), minute=59, second=59, microsecond=0)
        return start, end, f"{described} {name}"

    if period:
        h1, h2, name = period
        start = anchor.replace(hour=h1, minute=0, second=0, microsecond=0)
        end = anchor.replace(hour=min(h2, 23), minute=59, second=59, microsecond=0)
        return start, end, f"hôm nay {name}"

    return base_start, base_end, described


def parse_query(raw: str) -> dict:
    """Phân tích câu tiếng Việt thành bộ lọc. Luôn trả về `understood` để hiển thị lại."""
    text = strip_accents(raw or "")
    text = re.sub(r"\s+", " ", text).strip()

    label = None
    for coco_name, keywords in OBJECT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            label = coco_name
            break

    direction = None
    if any(kw in text for kw in DIRECTION_IN) and not any(
        kw in text for kw in ("di ra", "ra ngoai", "roi khoi")
    ):
        direction = "in"
    elif any(kw in text for kw in DIRECTION_OUT):
        direction = "out"

    time_from, time_to, time_label = parse_time_range(text)

    # Phần chữ còn lại (sau khi bỏ từ khoá đã hiểu) dùng để dò tên camera.
    residue = text
    for group in (
        [kw for kws in OBJECT_KEYWORDS.values() for kw in kws],
        DIRECTION_IN, DIRECTION_OUT,
        ["hom qua", "hom nay", "tuan nay", "tuan truoc", "sang", "trua", "chieu",
         "toi", "dem", "ngay truoc", "ngay qua"],
    ):
        for kw in sorted(group, key=len, reverse=True):
            residue = residue.replace(kw, " ")
    residue = " ".join(w for w in residue.split() if w not in STOPWORDS and not w.isdigit())

    camera_id = None
    camera_name = None
    if residue:
        for camera in db.query("SELECT id, name, location FROM cameras"):
            haystack = strip_accents(f"{camera['name']} {camera['location']}")
            if any(word in haystack for word in residue.split() if len(word) >= 3):
                camera_id = camera["id"]
                camera_name = camera["name"]
                break

    understood = []
    if label:
        from .config import CLASS_LABELS_VI
        understood.append(f"đối tượng: {CLASS_LABELS_VI.get(label, label)}")
    if direction:
        understood.append(f"chiều: {'vào' if direction == 'in' else 'ra'}")
    if camera_name:
        understood.append(f"camera: {camera_name}")
    if time_label:
        understood.append(f"thời gian: {time_label}")

    return {
        "label": label,
        "direction": direction,
        "camera_id": camera_id,
        "from": time_from.isoformat(timespec="seconds") if time_from else None,
        "to": time_to.isoformat(timespec="seconds") if time_to else None,
        "understood": understood or ["không nhận ra tiêu chí — trả về sự kiện mới nhất"],
    }


def search_events(raw_query: str, limit: int = 200) -> dict:
    """Chạy truy vấn tiếng Việt và trả về sự kiện khớp kèm phần diễn giải."""
    filters = parse_query(raw_query)

    sql = [
        "SELECT e.*, c.name AS camera_name FROM events e",
        "LEFT JOIN cameras c ON c.id = e.camera_id",
        "WHERE 1=1",
    ]
    params: list = []
    if filters["label"]:
        sql.append("AND e.label = ?")
        params.append(filters["label"])
    if filters["direction"]:
        sql.append("AND e.direction = ?")
        params.append(filters["direction"])
    if filters["camera_id"]:
        sql.append("AND e.camera_id = ?")
        params.append(filters["camera_id"])
    if filters["from"]:
        sql.append("AND e.ts >= ?")
        params.append(filters["from"])
    if filters["to"]:
        sql.append("AND e.ts <= ?")
        params.append(filters["to"])
    sql.append("ORDER BY e.ts DESC LIMIT ?")
    params.append(limit)

    results = db.query(" ".join(sql), params)
    return {"query": raw_query, "filters": filters, "total": len(results), "results": results}
