"""Sinh tài liệu API từ hệ thống đang chạy, ghi ra `docs/api.md`.

Viết tay tài liệu kiểu dữ liệu là cách chắc chắn để nó lệch khỏi mã nguồn — dự án này
đã ba lần mắc đúng lỗi ấy với toạ độ vạch, hệ số vùng đệm và ngưỡng tin cậy. Vì vậy
tài liệu được **sinh ra**, không gõ tay: phần tham số vào lấy từ đặc tả OpenAPI mà
FastAPI tự dựng từ các lớp Pydantic, còn phần dữ liệu ra lấy bằng cách gọi thật từng
điểm cuối rồi suy ra kiểu từ phản hồi.

Cách suy kiểu từ phản hồi thật có một hạn chế phải nói rõ: trường nào đang mang giá trị
rỗng ở thời điểm chạy sẽ bị ghi là `null` thay vì kiểu thật của nó. Tài liệu vì vậy nên
sinh lại khi hệ thống có đủ dữ liệu — ít nhất một camera đang chạy, một pipeline đã đếm
được vài lượt, và một ngày đã có đoạn ghi hình.

    python scripts/sinh_tai_lieu_api.py
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
DICH = GOC / "docs" / "api.md"
GOC_API = "http://localhost:8000"

# Nhóm điểm cuối theo chức năng để tài liệu đọc được, thay vì xếp theo thứ tự chữ cái.
NHOM = [
    ("Camera", "/api/cameras", "Khai báo nguồn video và theo dõi trạng thái luồng."),
    ("Pipeline", "/api/pipelines", "Cấu hình bài toán AI chạy trên từng camera."),
    ("Sự kiện và thống kê", "/api/events", "Lượt qua vạch, cảnh báo, số đếm theo giờ."),
    ("Tìm kiếm", "/api/search", "Tra cứu sự kiện bằng câu tiếng Việt."),
    ("Xem lại", "/api/playback", "Dòng thời gian và đoạn ghi hình đã lưu."),
    ("Quản trị", "/api/admin", "Cấu hình hệ thống và dọn dữ liệu."),
    ("Trợ lý AI", "/api/ai", "Bộ mô tả công cụ để trợ lý AI gọi được hệ thống."),
]

# Tham số mẫu để gọi thử các điểm cuối cần đối số. Điền lúc chạy từ dữ liệu thật.
MAU: dict[str, str] = {}


#: Điểm cuối trả về luồng vô tận — gọi thử sẽ treo cho tới lúc hết giờ chờ.
KHONG_GOI = ("/stream",)


def _goi(duong_dan: str, method: str = "GET", than=None):
    """Gọi một điểm cuối. Trả None nếu lỗi hoặc phản hồi không phải JSON.

    Phải xét `Content-Type` trước khi phân tích: các điểm cuối trả ảnh JPEG hay video
    MP4 sẽ làm `json.loads` ném `UnicodeDecodeError` chứ không phải `JSONDecodeError`,
    nên bắt riêng lỗi JSON là không đủ.
    """
    if any(duong_dan.endswith(x) for x in KHONG_GOI):
        return None
    url = f"{GOC_API}{duong_dan}"
    du_lieu = json.dumps(than).encode() if than is not None else None
    req = urllib.request.Request(
        url, method=method, data=du_lieu,
        headers={"Content-Type": "application/json"} if du_lieu else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if "json" not in (r.headers.get("Content-Type") or ""):
                return None
            noi = r.read()
            return json.loads(noi) if noi else None
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError, UnicodeDecodeError, TimeoutError, OSError):
        return None


def _kieu(v, sau: int = 0) -> str:
    """Tên kiểu dữ liệu ở dạng người đọc được, đệ quy vào trong mảng và đối tượng."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        if not v:
            return "array"
        return f"array<{_kieu(v[0], sau + 1)}>"
    if isinstance(v, dict):
        if sau >= 2:
            return "object"
        ben_trong = ", ".join(f"{k}: {_kieu(x, sau + 1)}" for k, x in list(v.items())[:6])
        con = ", …" if len(v) > 6 else ""
        return "{" + ben_trong + con + "}"
    return type(v).__name__


def _gop_kieu(cac_kieu: set[str]) -> str:
    """Gộp các kiểu quan sát được của cùng một trường thành một mô tả.

    Suy kiểu từ đúng một phần tử cho kết quả sai lệch: trường nào tình cờ rỗng ở phần
    tử đầu sẽ bị ghi là `null` thay vì kiểu thật. Duyệt hết mảng rồi hợp nhất thì
    `null | string` mới phản ánh đúng rằng trường đó cho phép rỗng.
    """
    cac_kieu = set(cac_kieu)
    if len(cac_kieu) > 1:
        cac_kieu.discard("array")          # mảng rỗng bị lấn át bởi mảng có phần tử
    if len(cac_kieu) > 2:
        cu_the = {t for t in cac_kieu if t != "null"}
        if len(cu_the) > 1:                # nhiều dạng object khác nhau, nói chung chung
            cu_the = {"object" if t.startswith("{") else t for t in cu_the}
        cac_kieu = cu_the | ({"null"} if "null" in cac_kieu else set())
    return " | ".join(sorted(cac_kieu, key=lambda t: (t == "null", t)))


def _bang_truong(mau) -> list[str]:
    """Bảng Markdown mô tả từng trường, gộp kiểu qua mọi phần tử của mảng."""
    if isinstance(mau, list):
        if not mau:
            return ["_Mảng rỗng lúc sinh tài liệu — chạy lại khi có dữ liệu._", ""]
        phan_tu = [x for x in mau if isinstance(x, dict)]
        if not phan_tu:
            return [f"Mảng các giá trị kiểu `{_kieu(mau[0])}`.", ""]
    else:
        if not isinstance(mau, dict):
            return [f"Trả về trực tiếp một giá trị kiểu `{_kieu(mau)}`.", ""]
        phan_tu = [mau]

    kieu: dict[str, set[str]] = {}
    vi_du: dict[str, Any] = {}
    for x in phan_tu:
        for k, v in x.items():
            kieu.setdefault(k, set()).add(_kieu(v))
            # Ưu tiên ví dụ khác rỗng: `null` không cho biết gì về trường đó.
            if k not in vi_du or (vi_du[k] in (None, [], {}, "") and v not in (None, [], {}, "")):
                vi_du[k] = v

    dong = ["| Trường | Kiểu | Ví dụ |", "|---|---|---|"]
    for k in kieu:
        vd = json.dumps(vi_du[k], ensure_ascii=False)
        if len(vd) > 46:
            vd = vd[:43] + "…"
        dong.append(f"| `{k}` | `{_gop_kieu(kieu[k])}` | `{vd}` |")
    dong.append("")
    if len(phan_tu) > 1:
        dong += [f"_Kiểu gộp từ {len(phan_tu)} phần tử trong phản hồi thật._", ""]
    return dong


def _nap_mau():
    """Lấy vài mã định danh thật để gọi thử các điểm cuối có tham số đường dẫn."""
    cams = _goi("/api/cameras") or []
    if cams:
        MAU["camera_id"] = cams[0]["id"]
    pls = _goi("/api/pipelines") or []
    if pls:
        MAU["pipeline_id"] = pls[0]["id"]
    evs = _goi("/api/events?limit=1") or []
    if evs:
        MAU["event_id"] = evs[0]["id"]
    if "camera_id" in MAU:
        segs = (_goi(f"/api/playback/segments?camera_id={MAU['camera_id']}") or {})
        ds = segs.get("segments") or []
        if ds:
            MAU["segment_id"] = ds[0]["id"]


def _duong_dan_thuc(mau_duong_dan: str) -> str | None:
    """Thay `{camera_id}` bằng mã thật. Trả None nếu thiếu mẫu."""
    ra = mau_duong_dan
    for ten, gia_tri in MAU.items():
        ra = ra.replace("{" + ten + "}", gia_tri)
    if "{" in ra:
        return None
    return ra


def main() -> None:
    dac_ta = _goi("/openapi.json")
    if not dac_ta:
        raise SystemExit(f"Không gọi được {GOC_API}/openapi.json — backend đã chạy chưa?")
    _nap_mau()

    d = [
        "# Tài liệu API",
        "",
        "> Tệp này **sinh tự động** bằng `scripts/sinh_tai_lieu_api.py`, đừng sửa tay.",
        "> Phần tham số vào lấy từ đặc tả OpenAPI; phần dữ liệu ra lấy bằng cách gọi",
        "> thật từng điểm cuối trên hệ thống đang chạy rồi suy ra kiểu.",
        "",
        f"Sinh lúc {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
        f"{sum(len(v) for v in dac_ta['paths'].values())} điểm cuối · "
        f"gốc `{GOC_API}`",
        "",
        "## Quy ước chung",
        "",
        "- Mọi thân yêu cầu và phản hồi đều là JSON mã hoá UTF-8.",
        "- Toạ độ vạch đếm và vùng **chuẩn hoá về 0..1** theo chiều rộng và chiều cao",
        "  khung hình, nên không phụ thuộc độ phân giải camera.",
        "- Mốc thời gian theo ISO 8601 giờ địa phương, ví dụ `2026-08-05T14:30:00`.",
        "- Lỗi trả về mã HTTP tương ứng kèm thân `{\"detail\": \"...\"}`.",
        "- Điểm cuối trả về ảnh hoặc video dùng `image/jpeg`, `video/mp4` hoặc",
        "  `multipart/x-mixed-replace` chứ không phải JSON; các mục đó ghi rõ bên dưới.",
        "",
    ]

    # ── Lược đồ dùng chung ──
    d += ["## Lược đồ dùng chung", ""]
    for ten, sch in sorted((dac_ta.get("components", {}).get("schemas") or {}).items()):
        if ten.startswith("HTTPValidation") or ten == "ValidationError":
            continue
        d += [f"### `{ten}`", ""]
        if sch.get("description"):
            d += [sch["description"], ""]
        thuoc = sch.get("properties") or {}
        if thuoc:
            bat_buoc = set(sch.get("required") or [])
            d += ["| Trường | Kiểu | Bắt buộc | Mặc định |", "|---|---|---|---|"]
            for k, v in thuoc.items():
                d.append(
                    f"| `{k}` | `{_kieu_lc(v)}` | "
                    f"{'có' if k in bat_buoc else '—'} | "
                    f"{'`' + json.dumps(v['default'], ensure_ascii=False) + '`' if 'default' in v else '—'} |"
                )
            d.append("")

    d += _huong_dan_ai()

    # ── Từng nhóm điểm cuối ──
    for ten_nhom, tien_to, mo_ta in NHOM:
        cac = {p: o for p, o in dac_ta["paths"].items() if p.startswith(tien_to)}
        if not cac:
            continue
        d += [f"## {ten_nhom}", "", mo_ta, ""]
        for duong_dan in sorted(cac):
            for method, op in sorted(cac[duong_dan].items()):
                d += _mo_ta_diem_cuoi(duong_dan, method, op)

    DICH.parent.mkdir(parents=True, exist_ok=True)
    DICH.write_text("\n".join(d), encoding="utf-8")
    print(f"  đã sinh {DICH.relative_to(GOC)} — {len(d)} dòng")


def _huong_dan_ai() -> list[str]:
    """Phần hướng dẫn tích hợp trợ lý AI, kèm danh sách công cụ lấy từ hệ thống thật."""
    tools = _goi("/api/ai/tools") or {}
    d = [
        "## Tích hợp trợ lý AI",
        "",
        "Trợ lý AI không đọc tài liệu này rồi tự suy ra cách gọi; nó cần bộ **mô tả công",
        "cụ** dạng máy đọc được. Hai điểm cuối dưới đây cung cấp đúng thứ đó.",
        "",
        "### Luồng gọi",
        "",
        "```",
        "1. GET  /api/ai/tools            → lấy danh sách công cụ",
        "2. gửi danh sách đó cho mô hình cùng câu hỏi của người dùng",
        "3. mô hình chọn công cụ và tham số",
        "4. POST /api/ai/call             → thực thi, nhận kết quả",
        "5. gửi kết quả lại cho mô hình  → mô hình diễn đạt thành câu trả lời",
        "```",
        "",
        "### Công cụ hiện có",
        "",
    ]
    if tools.get("cong_cu"):
        d += ["| Tên | Tham số | Dùng khi |", "|---|---|---|"]
        for c in tools["cong_cu"]:
            ts = (c.get("input_schema") or {}).get("properties") or {}
            bb = set((c.get("input_schema") or {}).get("required") or [])
            ten_ts = ", ".join(f"`{k}`" + ("\\*" if k in bb else "") for k in ts) or "—"
            d.append(f"| `{c['name']}` | {ten_ts} | {c['description'].split('.')[0]}. |")
        d += ["", "Tham số đánh dấu `*` là bắt buộc.", ""]

    d += [
        "### Chỉ đọc, không ghi",
        "",
        "Bộ công cụ **chỉ gồm các thao tác đọc**. Trợ lý không thêm, sửa hay xoá được gì.",
        "Đây là quyết định có chủ ý: mô hình ngôn ngữ có thể hiểu sai ý người dùng, mà",
        "hiểu sai một câu hỏi thì chỉ ra câu trả lời sai, còn hiểu sai một lệnh xoá thì",
        "mất dữ liệu. Ai cần thao tác ghi thì gọi thẳng điểm cuối tương ứng.",
        "",
        "### Xử lý lỗi",
        "",
        "`POST /api/ai/call` **luôn trả về HTTP 200**, kể cả khi lời gọi sai. Trạng thái",
        "nằm ở trường `thanh_cong`, còn `loi` mô tả sai ở đâu và cách sửa:",
        "",
        "```json",
        '{"thanh_cong": false,',
        ' "loi": "Tham số không hợp lệ: gio. Công cụ này nhận: camera_id, pipeline_id, so_gio"}',
        "```",
        "",
        "Lý do không dùng mã lỗi HTTP: phía gọi là mô hình ngôn ngữ, nó cần **đọc được**",
        "thông báo để thử lại cho đúng. Một mã 422 trần không nói lên điều gì.",
        "",
        "### Ví dụ đầy đủ",
        "",
        "```python",
        "import anthropic, requests",
        "",
        'GOC = "http://localhost:8000"',
        'cong_cu = requests.get(f"{GOC}/api/ai/tools").json()["cong_cu"]',
        "",
        "client = anthropic.Anthropic()",
        'tin_nhan = [{"role": "user", "content": "Sáng nay có bao nhiêu người đi qua cổng?"}]',
        "",
        "while True:",
        "    tl = client.messages.create(",
        '        model="claude-sonnet-5", max_tokens=1024,',
        "        tools=cong_cu, messages=tin_nhan,",
        "    )",
        '    tin_nhan.append({"role": "assistant", "content": tl.content})',
        '    if tl.stop_reason != "tool_use":',
        "        print(tl.content[0].text)",
        "        break",
        "",
        "    ket_qua = []",
        "    for khoi in tl.content:",
        '        if khoi.type != "tool_use":',
        "            continue",
        "        r = requests.post(",
        '            f"{GOC}/api/ai/call",',
        '            json={"ten": khoi.name, "tham_so": khoi.input},',
        "        ).json()",
        "        ket_qua.append({",
        '            "type": "tool_result", "tool_use_id": khoi.id,',
        '            "content": str(r.get("ket_qua") if r["thanh_cong"] else r["loi"]),',
        '            "is_error": not r["thanh_cong"],',
        "        })",
        '    tin_nhan.append({"role": "user", "content": ket_qua})',
        "```",
        "",
        "Định dạng OpenAI lấy bằng `GET /api/ai/tools?dinh_dang=openai` — nội dung như",
        "nhau, chỉ khác cách đặt tên khoá.",
        "",
    ]
    return d


def _kieu_lc(sch: dict) -> str:
    """Tên kiểu từ một mẩu lược đồ OpenAPI."""
    if "anyOf" in sch:
        return " | ".join(_kieu_lc(x) for x in sch["anyOf"])
    if "$ref" in sch:
        return sch["$ref"].rsplit("/", 1)[-1]
    t = sch.get("type")
    if t == "array":
        return f"array<{_kieu_lc(sch.get('items', {}))}>"
    if "enum" in sch:
        return " | ".join(json.dumps(x, ensure_ascii=False) for x in sch["enum"])
    return t or "any"


def _mo_ta_diem_cuoi(duong_dan: str, method: str, op: dict) -> list[str]:
    d = [f"### `{method.upper()} {duong_dan}`", ""]
    if op.get("summary"):
        d += [f"**{op['summary']}**", ""]
    if op.get("description"):
        d += [op["description"].strip().split("\n\n")[0], ""]

    # tham số
    ts = op.get("parameters") or []
    if ts:
        d += ["**Tham số**", "", "| Tên | Vị trí | Kiểu | Bắt buộc |", "|---|---|---|---|"]
        for t in ts:
            d.append(f"| `{t['name']}` | {t['in']} | `{_kieu_lc(t.get('schema', {}))}` | "
                     f"{'có' if t.get('required') else '—'} |")
        d.append("")

    # thân yêu cầu
    rb = op.get("requestBody")
    if rb:
        sch = (rb.get("content", {}).get("application/json", {}).get("schema") or {})
        ten = sch.get("$ref", "").rsplit("/", 1)[-1]
        if ten:
            d += [f"**Thân yêu cầu** — lược đồ [`{ten}`](#{ten.lower()})", ""]

    # dữ liệu trả về: gọi thật rồi suy kiểu
    if method == "get":
        thuc = _duong_dan_thuc(duong_dan)
        if thuc is None:
            d += ["**Trả về** — chưa lấy được mẫu (thiếu mã định danh để gọi thử).", ""]
        else:
            noi = _goi(thuc)
            if noi is None:
                d += ["**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).", ""]
            else:
                d += [f"**Trả về** `{_kieu(noi)}`" if not isinstance(noi, (dict, list))
                      else "**Trả về**", ""]
                d += _bang_truong(noi)
                vd = json.dumps(noi[0] if isinstance(noi, list) and noi else noi,
                                ensure_ascii=False, indent=2)
                if len(vd) < 1200:
                    d += ["<details><summary>Ví dụ phản hồi</summary>", "",
                          "```json", vd, "```", "", "</details>", ""]
    else:
        d += ["**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; "
              "thao tác xoá trả về `204 No Content`.", ""]
    return d


if __name__ == "__main__":
    main()
