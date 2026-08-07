"""Sinh tài liệu API từ hệ thống đang chạy, ghi ra `docs/api.md`.

Viết tay tài liệu kiểu dữ liệu là cách chắc chắn để nó lệch khỏi mã nguồn — dự án này
đã ba lần mắc đúng lỗi ấy với toạ độ vạch, hệ số vùng đệm và ngưỡng tin cậy. Vì vậy
tài liệu được **sinh ra**: tham số vào lấy từ đặc tả OpenAPI mà FastAPI tự dựng từ các
lớp Pydantic, còn kiểu trả về lấy bằng cách gọi thật từng điểm cuối rồi suy ra kiểu.

Tài liệu viết theo hướng tra cứu nhanh: mỗi đối tượng trả về mô tả **đúng một lần**,
phần điểm cuối chỉ trỏ tới tên đối tượng. Bản trước liệt kê đầy đủ trường cho từng
điểm cuối nên dài gần một nghìn dòng mà phần lớn là lặp lại.

    python scripts/sinh_tai_lieu_api.py
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

GOC = Path(__file__).resolve().parent.parent
DICH = GOC / "docs" / "api.md"
GOC_API = "http://localhost:8000"

NHOM = [
    ("Camera", "/api/cameras"),
    ("Pipeline", "/api/pipelines"),
    ("Sự kiện & thống kê", "/api/events"),
    ("Tìm kiếm", "/api/search"),
    ("Xem lại", "/api/playback"),
    ("Quản trị", "/api/admin"),
    ("Trợ lý AI", "/api/ai"),
]

#: Đặt tên cho các đối tượng trả về hay lặp lại, khoá là đường dẫn lấy mẫu.
DAT_TEN = {
    "/api/cameras": "Camera",
    "/api/pipelines": "Pipeline",
    "/api/events": "Event",
}

#: Điểm cuối trả về luồng vô tận — gọi thử sẽ treo cho tới lúc hết giờ chờ.
KHONG_GOI = ("/stream",)

MAU: dict[str, str] = {}


def _goi(duong_dan: str):
    """Gọi một điểm cuối GET. Trả None nếu lỗi hoặc phản hồi không phải JSON.

    Phải xét `Content-Type` trước khi phân tích: điểm cuối trả ảnh JPEG hay video MP4
    làm `json.loads` ném `UnicodeDecodeError` chứ không phải `JSONDecodeError`.
    """
    if any(duong_dan.endswith(x) for x in KHONG_GOI):
        return None
    try:
        with urllib.request.urlopen(f"{GOC_API}{duong_dan}", timeout=20) as r:
            if "json" not in (r.headers.get("Content-Type") or ""):
                return None
            noi = r.read()
            return json.loads(noi) if noi else None
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError,
            UnicodeDecodeError, TimeoutError, OSError):
        return None


def _kieu(v, sau: int = 0) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return f"[{_kieu(v[0], sau + 1)}]" if v else "[]"
    if isinstance(v, dict):
        return "object" if sau >= 1 else "{…}"
    return type(v).__name__


def _gop(cac: set[str]) -> str:
    """Gộp các kiểu quan sát được của cùng một trường.

    Suy kiểu từ một phần tử duy nhất cho kết quả sai: trường tình cờ rỗng ở phần tử đầu
    sẽ bị ghi là `null` thay vì kiểu thật. Duyệt hết mảng rồi hợp nhất thì `str | null`
    mới phản ánh đúng rằng trường đó cho phép rỗng.
    """
    cac = set(cac)
    if len(cac) > 1:
        cac.discard("[]")
    cu_the = {t for t in cac if t != "null"}
    if len(cu_the) > 1:
        cu_the = {"object" if t.startswith("{") else t for t in cu_the}
    cac = cu_the | ({"null"} if "null" in cac else set())
    return " \\| ".join(sorted(cac, key=lambda t: (t == "null", t))) or "null"


def _truong(mau) -> list[tuple[str, str]]:
    """Danh sách (tên trường, kiểu) suy từ phản hồi, gộp qua mọi phần tử của mảng."""
    ds = [x for x in mau if isinstance(x, dict)] if isinstance(mau, list) else [mau]
    ds = [x for x in ds if isinstance(x, dict)]
    kieu: dict[str, set[str]] = {}
    for x in ds:
        for k, v in x.items():
            kieu.setdefault(k, set()).add(_kieu(v))
    return [(k, _gop(v)) for k, v in kieu.items()]


def _kieu_lc(sch: dict) -> str:
    """Tên kiểu từ một mẩu lược đồ OpenAPI."""
    if "anyOf" in sch:
        return " \\| ".join(_kieu_lc(x) for x in sch["anyOf"])
    if "$ref" in sch:
        return sch["$ref"].rsplit("/", 1)[-1]
    if "enum" in sch:
        return " \\| ".join(f"`{x}`" for x in sch["enum"])
    t = sch.get("type")
    if t == "array":
        return f"[{_kieu_lc(sch.get('items', {}))}]"
    return {"string": "str", "integer": "int", "number": "float",
            "boolean": "bool"}.get(t, t or "any")


def _nap_mau():
    for khoa, dd, lay in (
        ("camera_id", "/api/cameras", lambda r: r[0]["id"] if r else None),
        ("pipeline_id", "/api/pipelines", lambda r: r[0]["id"] if r else None),
        ("event_id", "/api/events?limit=1", lambda r: r[0]["id"] if r else None),
    ):
        v = lay(_goi(dd) or [])
        if v:
            MAU[khoa] = v
    if "camera_id" in MAU:
        ds = (_goi(f"/api/playback/segments?camera_id={MAU['camera_id']}") or {}).get("segments")
        if ds:
            MAU["segment_id"] = ds[0]["id"]


def _thuc(mau_dd: str) -> str | None:
    ra = mau_dd
    for ten, gt in MAU.items():
        ra = ra.replace("{" + ten + "}", gt)
    return None if "{" in ra else ra


def main() -> None:
    dac_ta = _goi("/openapi.json")
    if not dac_ta:
        raise SystemExit(f"Không gọi được {GOC_API}/openapi.json — backend đã chạy chưa?")
    _nap_mau()
    paths = dac_ta["paths"]
    sc = dac_ta.get("components", {}).get("schemas") or {}

    d = [
        "# Tài liệu API — VisionOS",
        "",
        f"*Sinh tự động bằng `scripts/sinh_tai_lieu_api.py` lúc "
        f"{datetime.now().strftime('%d/%m/%Y %H:%M')} · "
        f"{sum(len(v) for v in paths.values())} điểm cuối · gốc `{GOC_API}` · **đừng sửa tay***",
        "",
        "JSON UTF-8. Thời gian ISO 8601 giờ địa phương (`2026-08-06T14:30:00`). "
        "Toạ độ vạch và vùng chuẩn hoá 0..1 theo kích thước khung hình. "
        "Lỗi trả mã HTTP tương ứng kèm `{\"detail\": \"…\"}`.",
        "",
    ]

    # ── Đối tượng trả về ──
    d += ["## Đối tượng trả về", ""]
    for dd, ten in DAT_TEN.items():
        mau = _goi(dd)
        if not mau:
            continue
        d += [f"### {ten}", "", "| Trường | Kiểu |", "|---|---|"]
        d += [f"| `{k}` | `{t}` |" for k, t in _truong(mau)]
        d.append("")

    # ── Đối tượng gửi lên ──
    d += ["## Đối tượng gửi lên", ""]
    for ten in sorted(sc):
        if ten.startswith("HTTPValidation") or ten == "ValidationError":
            continue
        thuoc = sc[ten].get("properties") or {}
        if not thuoc:
            continue
        bb = set(sc[ten].get("required") or [])
        d += [f"### {ten}", "", "| Trường | Kiểu | Bắt buộc |", "|---|---|---|"]
        for k, v in thuoc.items():
            d.append(f"| `{k}` | `{_kieu_lc(v)}` | {'✓' if k in bb else ''} |")
        d.append("")

    # ── Điểm cuối ──
    d += ["## Điểm cuối", ""]
    for ten_nhom, tien_to in NHOM:
        cac = {p: o for p, o in paths.items() if p.startswith(tien_to)}
        if not cac:
            continue
        d += [f"### {ten_nhom}", "", "| Phương thức | Đường dẫn | Vào | Ra |", "|---|---|---|---|"]
        for dd in sorted(cac):
            for m, op in sorted(cac[dd].items()):
                d.append(f"| `{m.upper()}` | `{dd}` | {_vao(op)} | {_ra(dd, m, op)} |")
        d.append("")

    d += _huong_dan_ai()

    DICH.parent.mkdir(parents=True, exist_ok=True)
    DICH.write_text("\n".join(d), encoding="utf-8")
    print(f"  đã sinh {DICH.relative_to(GOC)} — {len(d)} dòng")


def _vao(op: dict) -> str:
    phan = []
    for t in op.get("parameters") or []:
        phan.append(f"`{t['name']}`" + ("" if t.get("required") else "?"))
    rb = op.get("requestBody")
    if rb:
        sch = (rb.get("content", {}).get("application/json", {}).get("schema") or {})
        ten = sch.get("$ref", "").rsplit("/", 1)[-1]
        if ten:
            phan.append(f"body `{ten}`")
    return ", ".join(phan) or "—"


#: Kiểu trả về của các thao tác ghi. Không gọi thử được như GET nên tra từ mã nguồn:
#: mọi thao tác trên camera đều đi qua `_with_runtime`, trên pipeline qua `_shape`.
RA_GHI = {
    "/api/cameras": "Camera",
    "/api/cameras/{camera_id}": "Camera",
    "/api/cameras/{camera_id}/toggle": "Camera",
    "/api/pipelines": "Pipeline",
    "/api/pipelines/{pipeline_id}": "Pipeline",
    "/api/pipelines/{pipeline_id}/start": "Pipeline",
    "/api/pipelines/{pipeline_id}/stop": "Pipeline",
    "/api/pipelines/{pipeline_id}/reset": "Pipeline",
    "/api/cameras/probe": "{ok, message, width, height, fps, elapsed_ms}",
    "/api/pipelines/preview-prompt": "{prompt, filter_text, query, direction, uses_la, …}",
    "/api/events/{event_id}": "Event",
}


def _ra(duong_dan: str, method: str, op: dict) -> str:
    if method != "get":
        if method == "delete":
            return "`204`"
        ten = RA_GHI.get(duong_dan)
        return f"`{ten}`" if ten else "object"
    if duong_dan in DAT_TEN:
        return f"`[{DAT_TEN[duong_dan]}]`"
    if duong_dan.endswith("snapshot"):
        return "`image/jpeg`"
    if duong_dan.endswith("stream"):
        return "`multipart/x-mixed-replace`"
    if duong_dan.endswith(("video", "download")):
        return "`video/mp4`"
    thuc = _thuc(duong_dan)
    if thuc is None:
        return "object"
    noi = _goi(thuc)
    if noi is None:
        return "binary"
    if isinstance(noi, list):
        return f"`[{{{', '.join(k for k, _ in _truong(noi)[:4])}, …}}]`" if noi else "`[]`"
    if isinstance(noi, dict):
        khoa = list(noi)[:5]
        return "`{" + ", ".join(khoa) + (", …" if len(noi) > 5 else "") + "}`"
    return f"`{_kieu(noi)}`"


def _huong_dan_ai() -> list[str]:
    tools = _goi("/api/ai/tools") or {}
    d = [
        "## Tích hợp trợ lý AI",
        "",
        "Trợ lý AI cần bộ mô tả công cụ dạng máy đọc được, không đọc tài liệu này.",
        "`GET /api/ai/tools` trả về bộ đó, `POST /api/ai/call` thực thi một lời gọi.",
        "",
    ]
    if tools.get("cong_cu"):
        d += ["| Công cụ | Tham số | Dùng khi |", "|---|---|---|"]
        for c in tools["cong_cu"]:
            ts = (c.get("input_schema") or {}).get("properties") or {}
            bb = set((c.get("input_schema") or {}).get("required") or [])
            ten = ", ".join(f"`{k}`" + ("" if k in bb else "?") for k in ts) or "—"
            d.append(f"| `{c['name']}` | {ten} | {c['description'].split('.')[0]}. |")
        d += ["", "`?` = tuỳ chọn. Thêm `?dinh_dang=openai` để lấy định dạng OpenAI.", ""]
    d += [
        "**Chỉ đọc.** Trợ lý không thêm, sửa hay xoá được gì — hiểu sai một câu hỏi thì",
        "chỉ ra câu trả lời sai, hiểu sai một lệnh xoá thì mất dữ liệu.",
        "",
        "**Lỗi luôn trả HTTP 200**, trạng thái ở `thanh_cong`, `loi` nói rõ cách sửa:",
        "",
        "```json",
        '{"thanh_cong": false,',
        ' "loi": "Tham số không hợp lệ: gio. Công cụ này nhận: camera_id, pipeline_id, so_gio"}',
        "```",
        "",
        "Phía gọi là mô hình ngôn ngữ, nó cần đọc được thông báo để thử lại cho đúng;",
        "một mã 422 trần không nói lên điều gì.",
        "",
        "```python",
        "cong_cu = requests.get(f\"{GOC}/api/ai/tools\").json()[\"cong_cu\"]",
        "tl = client.messages.create(model=\"claude-sonnet-5\", max_tokens=1024,",
        "                            tools=cong_cu, messages=tin_nhan)",
        "# với mỗi khối tool_use trong tl.content:",
        "r = requests.post(f\"{GOC}/api/ai/call\",",
        "                  json={\"ten\": khoi.name, \"tham_so\": khoi.input}).json()",
        "# trả r[\"ket_qua\"] (hoặc r[\"loi\"] kèm is_error) lại cho mô hình",
        "```",
        "",
    ]
    return d


if __name__ == "__main__":
    main()
