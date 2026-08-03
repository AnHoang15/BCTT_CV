"""Lịch chạy của pipeline.

Cho phép giới hạn AI chỉ hoạt động trong những khung giờ nhất định, ví dụ chỉ đếm
khách trong giờ mở cửa. Ngoài khung giờ, camera vẫn phát hình và vẫn ghi hình bình
thường — chỉ phần nhận diện và đếm là tạm nghỉ. Như vậy vừa tiết kiệm tài nguyên vừa
không tạo ra số liệu rác lúc cửa hàng đóng.

Cấu trúc lưu trong cơ sở dữ liệu:

    {
      "enabled": true,
      "slots": [
        {"days": [2, 3, 4, 5, 6], "from": "08:00", "to": "18:00"}
      ]
    }

Ngày trong tuần đánh số theo cách gọi của người Việt: 2 là thứ Hai, ..., 7 là thứ Bảy,
8 là Chủ nhật. Dùng quy ước này thay vì 0--6 của Python để dữ liệu đọc lên khớp luôn
với nhãn hiển thị trên giao diện.
"""
from __future__ import annotations

import json
from datetime import datetime

# Python: thứ Hai = 0 ... Chủ nhật = 6. Quy ước của ta: thứ Hai = 2 ... Chủ nhật = 8.
_WEEKDAY_OFFSET = 2

DAY_LABELS = {2: "T2", 3: "T3", 4: "T4", 5: "T5", 6: "T6", 7: "T7", 8: "CN"}


def parse(raw: str | None) -> dict | None:
    """Đọc cấu hình lịch từ chuỗi JSON. Trả về None nếu không có hoặc hỏng."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("enabled"):
        return None
    slots = [s for s in data.get("slots", []) if _valid_slot(s)]
    return {"enabled": True, "slots": slots} if slots else None


def _valid_slot(slot) -> bool:
    if not isinstance(slot, dict):
        return False
    if not slot.get("days"):
        return False
    return bool(_to_minutes(slot.get("from")) is not None
                and _to_minutes(slot.get("to")) is not None)


def _to_minutes(value) -> int | None:
    """'08:30' -> 510. Trả về None nếu không đúng định dạng."""
    if not isinstance(value, str) or ":" not in value:
        return None
    hh, _, mm = value.partition(":")
    try:
        hours, minutes = int(hh), int(mm)
    except ValueError:
        return None
    if not (0 <= hours <= 24 and 0 <= minutes < 60):
        return None
    return hours * 60 + minutes


def is_active(schedule: dict | None, now: datetime | None = None) -> bool:
    """Thời điểm `now` có nằm trong lịch chạy không. Không có lịch nghĩa là luôn chạy."""
    if not schedule:
        return True

    moment = now or datetime.now()
    today = moment.weekday() + _WEEKDAY_OFFSET
    minutes = moment.hour * 60 + moment.minute

    for slot in schedule["slots"]:
        start = _to_minutes(slot["from"])
        end = _to_minutes(slot["to"])
        if start is None or end is None:
            continue

        if start <= end:
            if today in slot["days"] and start <= minutes < end:
                return True
        else:
            # Khung giờ vắt qua nửa đêm, ví dụ 22:00 đến 06:00. Phần sau nửa đêm thuộc
            # về ngày hôm sau nên phải đối chiếu với ngày hôm trước.
            if today in slot["days"] and minutes >= start:
                return True
            yesterday = (moment.weekday() - 1) % 7 + _WEEKDAY_OFFSET
            if yesterday in slot["days"] and minutes < end:
                return True
    return False


def describe(schedule: dict | None) -> str:
    """Mô tả lịch bằng tiếng Việt để ghi nhật ký."""
    if not schedule:
        return "chạy liên tục 24/7"
    parts = []
    for slot in schedule["slots"]:
        days = " ".join(DAY_LABELS.get(d, str(d)) for d in sorted(slot["days"]))
        parts.append(f"{days} {slot['from']}–{slot['to']}")
    return "; ".join(parts)
