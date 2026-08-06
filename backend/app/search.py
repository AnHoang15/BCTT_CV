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
    # Hư từ và từ chỉ thời gian. Thiếu chúng thì phần dư đem đi dò tên camera còn
    # sót những chữ vô nghĩa, và chỉ cần một chữ trùng là gán nhầm camera: câu
    # "người đi ra tối qua" từng bị gán camera "Cổng ra vào" chỉ vì chữ "qua" trùng
    # với "lối đi bộ qua đường" trong phần vị trí.
    "cua", "qua", "roi", "vua", "moi", "gan", "day", "nay", "hom", "buoi",
    "ngay", "tuan", "truoc", "sau", "voi", "ve", "ma", "thi", "duoc", "bi", "ai",
    # "đi bộ" trong "người đi bộ" từng khớp với vị trí "Lối đi bộ qua đường" của
    # camera Cổng ra vào. Hai chữ này quá phổ thông để làm dấu hiệu nhận camera.
    "di", "bo",
}


def _co_tu(text: str, phrase: str) -> bool:
    """Câu có chứa cụm này theo đúng ranh giới từ hay không.

    Dùng `in` trần là nguồn của cả một họ lỗi: sau khi bỏ dấu thì "tối", "tôi" và
    "tới" đều thành `toi`, còn chữ "ca-me-ra" thì chứa sẵn `ra`. Hậu quả là câu
    "camera của tôi" bị hiểu thành "chiều: ra, buổi tối" rồi lặng lẽ cắt kết quả
    theo một khung giờ mà người dùng không hề yêu cầu.
    """
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


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

    # Buổi trong ngày.
    #
    # Chỉ nhận khi có neo rõ ràng: "buổi tối", "tối nay", "tối qua". Bắt trần chữ
    # `toi` là sai, vì bỏ dấu xong thì "tối", "tôi" (đại từ) và "tới" (đến) đều thành
    # một — câu vô hại như "camera của tôi" hay "từ 8h tới 15h" bị bó vào khung
    # 18h–24h mà giao diện vẫn báo là đã hiểu.
    BUOI = {
        "sang": (6, 12, "buổi sáng"), "trua": (11, 14, "buổi trưa"),
        "chieu": (12, 18, "buổi chiều"),
        "toi": (18, 24, "buổi tối"), "dem": (18, 24, "buổi tối"),
    }
    period = None
    m = re.search(r"buoi\s+(sang|trua|chieu|toi|dem)\b", text)
    if m:
        period = BUOI[m.group(1)]
    else:
        # "tối qua" là tối HÔM QUA. Trước đây chỉ bắt được chữ "tối" rồi mặc định
        # hôm nay, trả về đúng khung giờ nhưng sai hẳn một ngày.
        m = re.search(r"\b(sang|trua|chieu|toi|dem)\s+(nay|qua)\b", text)
        if m:
            period = BUOI[m.group(1)]
            if base_start is None:
                hom = now - timedelta(days=1) if m.group(2) == "qua" else now
                base_start, base_end = _day_bounds(hom)
                described = "hôm qua" if m.group(2) == "qua" else "hôm nay"

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

    # Một mốc giờ đơn: "lúc 12h", "12 giờ", "khoảng 9h" — hiểu là khung một tiếng.
    # Trước đây câu kiểu "người đi vào lúc 12h" bị bỏ qua phần giờ mà không báo gì,
    # nên người dùng tưởng đã lọc còn kết quả thì trả về cả ngày.
    #
    # Bỏ qua khi mốc giờ đứng sau "từ", "đến", "tới", "trước", "sau": những câu đó
    # nói về một khoảng mở chứ không phải một tiếng, hiểu thành khung một tiếng là
    # sai hẳn. Chưa xử lý được thì để `understood` báo không nhận ra, còn hơn im
    # lặng cắt kết quả theo một khung mà người dùng không hề yêu cầu.
    single = re.search(r"(?:luc|khoang)\s*(\d{1,2})\s*(?:h|gio)\b", text)
    if not single and not re.search(
        r"\b(?:tu|den|toi|truoc|sau)\s+\d{1,2}\s*(?:h|gio)\b", text
    ):
        single = re.search(r"\b(\d{1,2})\s*(?:h|gio)\b", text)
    if single:
        h = int(single.group(1)) % 24
        start = anchor.replace(hour=h, minute=0, second=0, microsecond=0)
        return start, start + timedelta(hours=1), \
            f"{described + ' ' if described else ''}{h}h–{h + 1}h".strip()

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

    # Chọn từ khoá DÀI NHẤT khớp được, không phải lớp đứng đầu từ điển.
    #
    # "người đi xe đạp" chứa cả "nguoi" lẫn "xe dap"; duyệt theo thứ tự từ điển thì
    # `person` đứng trước nên thoát ngay và cho ra nhãn Người, trong khi ý người
    # dùng rõ ràng là tìm xe đạp. Cụm dài hơn bao giờ cũng cụ thể hơn.
    label = None
    khop = [
        (len(kw), coco_name)
        for coco_name, keywords in OBJECT_KEYWORDS.items()
        for kw in keywords
        if _co_tu(text, kw)
    ]
    if khop:
        label = max(khop)[1]

    direction = None
    if any(_co_tu(text, kw) for kw in DIRECTION_IN) and not any(
        _co_tu(text, kw) for kw in ("di ra", "ra ngoai", "roi khoi")
    ):
        direction = "in"
    elif any(_co_tu(text, kw) for kw in DIRECTION_OUT):
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
            residue = re.sub(
                rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", " ", residue
            )
    residue = " ".join(w for w in residue.split() if w not in STOPWORDS and not w.isdigit())

    # Dò camera từ phần chữ còn lại.
    #
    # Đòi hỏi bằng chứng đủ mạnh: hoặc một chữ dài từ bốn ký tự, hoặc hai chữ cùng
    # trùng. Điều kiện cũ — chỉ cần một chữ ba ký tự nằm đâu đó trong tên hay vị trí
    # — quá lỏng: "của" bỏ dấu thành "cua" khớp ngay với "Cửa tàu điện ngầm", và
    # người dùng nhận về kết quả của một camera họ không hề nhắc tới.
    camera_id = None
    camera_name = None
    if residue:
        for camera in db.query("SELECT id, name, location FROM cameras"):
            haystack = strip_accents(f"{camera['name']} {camera['location']}")
            trung = [w for w in set(residue.split())
                     if len(w) >= 2 and _co_tu(haystack, w)]
            if any(len(w) >= 3 for w in trung) or len(trung) >= 2:
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


def search_events(raw_query: str, limit: int = 200,
                  camera_id: str | None = None) -> dict:
    """Chạy truy vấn tiếng Việt và trả về sự kiện khớp kèm phần diễn giải.

    `camera_id` là camera người dùng đang chọn trên giao diện. Trước đây tham số này
    không tồn tại: chọn camera nào thì tìm kiếm cũng trả về sự kiện của mọi camera,
    trong khi ô chọn ngay phía trên vẫn hiển thị tên camera đã chọn.

    Câu lệnh có nêu rõ tên camera thì phần đó thắng, vì đó là ý định nói ra thành
    lời, cụ thể hơn một lựa chọn còn sót lại trên giao diện.
    """
    filters = parse_query(raw_query)
    if camera_id and not filters["camera_id"]:
        filters["camera_id"] = camera_id
        row = db.query_one("SELECT name FROM cameras WHERE id=?", (camera_id,))
        if row:
            filters["understood"] = [
                u for u in filters["understood"] if not u.startswith("không nhận ra")
            ] + [f"camera: {row['name']} (đang chọn)"]

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
    return {
        "query": raw_query,
        "filters": filters,
        "total": len(results),
        "results": results,
        "hint": _giai_thich_rong(filters) if not results else None,
    }


def _giai_thich_rong(filters: dict) -> str | None:
    """Vì sao không có kết quả — nói rõ thay vì để người dùng tự đoán.

    Trang xem lại được trình bày như tra cứu theo camera, nên không có kết quả trông
    y hệt như "camera này không có đối tượng đó đi qua". Sự thật có thể khác hẳn:
    hệ thống chỉ ghi sự kiện cho những lớp đối tượng mà một pipeline được cấu hình
    để theo dõi. Chưa pipeline nào để ý tới xe đạp thì cơ sở dữ liệu không có gì để
    tìm, dù camera quay được cả trăm chiếc.
    """
    label = filters.get("label")
    if not label:
        return None

    from .config import CLASS_LABELS_VI, COCO_CLASSES
    ten = CLASS_LABELS_VI.get(label, label)

    if label not in COCO_CLASSES:
        return f"Hệ thống chưa nhận diện được {ten}."

    rows = db.query("SELECT camera_id, active FROM pipelines")
    if filters.get("camera_id"):
        rows = [r for r in rows if r["camera_id"] == filters["camera_id"]]
    if not rows:
        return ("Camera này chưa có pipeline nào nên chưa ghi được sự kiện. "
                "Vào Cấu hình để tạo một pipeline cho nó.")
    if not any(r["active"] for r in rows):
        return ("Pipeline của camera này đang tắt nên không ghi sự kiện mới. "
                "Vào Cấu hình và bấm Chạy.")

    # Tới đây thì pipeline có chạy và hệ thống ghi nhận đủ cả sáu lớp, nên nguyên
    # nhân duy nhất còn lại là chưa có đối tượng loại đó đi qua vạch.
    #
    # Không khuyên người dùng đi thêm lớp vào mục "Đối tượng cần theo dõi" nữa: từ
    # bản tách ghi-nhận khỏi đếm, mục đó chỉ quyết định con số hiển thị chứ không
    # còn quyết định dữ liệu nào được lưu. Lời khuyên cũ giờ vừa thừa vừa gây hiểu
    # nhầm rằng phải cấu hình trước mới tra cứu được.
    co_du_lieu_cu = db.query_one(
        "SELECT 1 AS x FROM events WHERE label=? LIMIT 1", (label,)
    )
    them = "" if co_du_lieu_cu else (
        " Dữ liệu ghi trước hôm nay chỉ có Người, vì bản cũ chỉ lưu lớp được cấu hình"
        " đếm; từ giờ hệ thống lưu đủ cả sáu lớp."
    )
    dau = "trên camera này" if filters.get("camera_id") else "trên camera nào"
    return f"Chưa ghi nhận lượt {ten} nào cắt vạch {dau}.{them}"
