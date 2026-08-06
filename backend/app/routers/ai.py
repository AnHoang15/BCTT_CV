"""Cổng cho trợ lý AI gọi vào hệ thống.

Một trợ lý AI không đọc được tài liệu API rồi tự suy ra cách gọi; nó cần bộ **mô tả
công cụ** dạng máy đọc được, gồm tên, mô tả bằng lời và lược đồ tham số. Điểm cuối
`/api/ai/tools` trả về đúng thứ đó theo định dạng dùng chung của các nhà cung cấp mô
hình hiện nay, còn `/api/ai/call` thực thi một lời gọi và trả kết quả.

Nhờ vậy câu hỏi kiểu *"sáng nay có bao nhiêu người đi qua cổng?"* được trợ lý xử lý
thành: chọn công cụ `tim_kiem_su_kien`, truyền `cau_hoi="người đi vào hôm nay buổi
sáng"`, đọc kết quả rồi diễn đạt lại thành câu trả lời.

**Chỉ mở các công cụ chỉ đọc.** Trợ lý không thêm, sửa hay xoá được gì. Đây là quyết
định có chủ ý: mô hình ngôn ngữ có thể hiểu sai ý người dùng, và hiểu sai một câu hỏi
thì chỉ ra câu trả lời sai, còn hiểu sai một lệnh xoá thì mất dữ liệu. Ai cần thao tác
ghi thì gọi thẳng API tương ứng.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import db, manager, search

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ── Các hàm công cụ ──────────────────────────────────────────────────────────
def _liet_ke_camera() -> list[dict]:
    ra = []
    for c in db.query("SELECT id, name, location, kind, enabled FROM cameras ORDER BY name"):
        worker = manager.get(c["id"])
        ra.append({
            **c,
            "dang_chay": worker is not None and worker.is_alive(),
            "trang_thai": worker.status if worker else "offline",
        })
    return ra


def _liet_ke_pipeline(camera_id: str | None = None) -> list[dict]:
    cau = ("SELECT p.id, p.name, p.camera_id, p.task, p.mode, p.classes, c.name AS camera_name "
           "FROM pipelines p LEFT JOIN cameras c ON c.id = p.camera_id")
    tham: tuple = ()
    if camera_id:
        cau += " WHERE p.camera_id = ?"
        tham = (camera_id,)

    # Một camera chạy được nhiều pipeline, nên phải tra đúng phần trạng thái của
    # pipeline đang xét trong `pipelines[]` chứ không lấy các trường ở cấp ngoài cùng.
    dem_trang_thai: dict[str, set[str]] = {}
    ra = []
    for p in db.query(cau + " ORDER BY p.name", tham):
        cam = p["camera_id"]
        if cam not in dem_trang_thai:
            worker = manager.get(cam)
            tt = worker.snapshot_state() if worker else {}
            dem_trang_thai[cam] = {
                x.get("pipeline_id") for x in tt.get("pipelines", [])
            }
        ra.append({**p, "dang_chay": p["id"] in dem_trang_thai[cam]})
    return ra


def _so_dem(pipeline_id: str | None = None, camera_id: str | None = None,
            so_gio: int = 24) -> dict:
    dieu_kien = ["ts >= datetime('now', 'localtime', ?)"]
    tham: list[Any] = [f"-{int(so_gio)} hours"]
    if pipeline_id:
        dieu_kien.append("pipeline_id = ?")
        tham.append(pipeline_id)
    if camera_id:
        dieu_kien.append("camera_id = ?")
        tham.append(camera_id)
    # `in_delta`/`out_delta` là số lượt phát sinh giữa hai lần ghi, cộng lại được tổng
    # trong khoảng. Dùng `in_total` sẽ sai vì đó là số dồn từ lúc pipeline khởi động,
    # và nó bị đặt lại mỗi khi video tệp phát hết một vòng.
    r = db.query_one(
        "SELECT COALESCE(SUM(in_delta), 0) AS vao, COALESCE(SUM(out_delta), 0) AS ra, "
        "COUNT(*) AS so_ban_ghi FROM counts WHERE " + " AND ".join(dieu_kien),
        tuple(tham),
    ) or {}
    return {"vao": r.get("vao", 0), "ra": r.get("ra", 0),
            "so_gio": so_gio, "so_ban_ghi": r.get("so_ban_ghi", 0)}


def _tim_kiem_su_kien(cau_hoi: str, camera_id: str | None = None,
                      gioi_han: int = 20) -> dict:
    kq = search.search_events(cau_hoi, limit=min(int(gioi_han), 100), camera_id=camera_id)
    # Bỏ đường dẫn ảnh khỏi kết quả: trợ lý không hiển thị được ảnh, giữ lại chỉ tốn
    # ngữ cảnh. Ai cần ảnh thì gọi /api/events/{id}/snapshot.
    return {
        "tong": kq.get("total", 0),
        "he_thong_hieu": (kq.get("filters") or {}).get("understood", []),
        "goi_y": kq.get("hint"),
        "ket_qua": [
            {k: v for k, v in e.items() if k not in ("snapshot",)}
            for e in (kq.get("results") or [])
        ],
    }


def _tom_tat_he_thong() -> dict:
    cam = db.query_one("SELECT COUNT(*) AS n FROM cameras") or {}
    pl = db.query_one("SELECT COUNT(*) AS n FROM pipelines") or {}
    sk = db.query_one(
        "SELECT COUNT(*) AS n FROM events WHERE ts >= datetime('now','localtime','-24 hours')"
    ) or {}
    return {
        "so_camera": cam.get("n", 0),
        "so_pipeline": pl.get("n", 0),
        "camera_dang_chay": sum(1 for c in _liet_ke_camera() if c["dang_chay"]),
        "su_kien_24h": sk.get("n", 0),
    }


# ── Bộ mô tả công cụ ─────────────────────────────────────────────────────────
# Mô tả viết bằng tiếng Việt và nói rõ *khi nào dùng*, không chỉ *làm gì*. Mô hình chọn
# công cụ dựa trên phần mô tả này, nên một câu mơ hồ ở đây gây gọi nhầm công cụ.
CONG_CU: dict[str, dict] = {
    "liet_ke_camera": {
        "ham": _liet_ke_camera,
        "mo_ta": "Liệt kê mọi camera trong hệ thống kèm trạng thái đang chạy hay đã "
                 "tắt. Dùng khi cần biết có những camera nào, hoặc cần lấy mã camera "
                 "để truyền cho công cụ khác.",
        "tham_so": {"type": "object", "properties": {}, "required": []},
    },
    "liet_ke_pipeline": {
        "ham": _liet_ke_pipeline,
        "mo_ta": "Liệt kê các pipeline AI đã cấu hình, kèm bài toán và nhóm đối tượng "
                 "mà mỗi pipeline theo dõi. Dùng khi cần biết hệ thống đang đếm gì.",
        "tham_so": {
            "type": "object",
            "properties": {
                "camera_id": {"type": "string",
                              "description": "Chỉ lấy pipeline của một camera. Bỏ trống "
                                             "để lấy tất cả."},
            },
            "required": [],
        },
    },
    "lay_so_dem": {
        "ham": _so_dem,
        "mo_ta": "Lấy tổng số lượt Vào và Ra trong N giờ gần nhất. Dùng cho câu hỏi về "
                 "số lượng như 'hôm nay bao nhiêu người vào', 'lưu lượng 3 tiếng qua'.",
        "tham_so": {
            "type": "object",
            "properties": {
                "pipeline_id": {"type": "string", "description": "Lọc theo một pipeline."},
                "camera_id": {"type": "string", "description": "Lọc theo một camera."},
                "so_gio": {"type": "integer", "default": 24,
                           "description": "Khoảng thời gian tính ngược từ hiện tại."},
            },
            "required": [],
        },
    },
    "tim_kiem_su_kien": {
        "ham": _tim_kiem_su_kien,
        "mo_ta": "Tra cứu sự kiện bằng câu tiếng Việt tự nhiên, ví dụ 'người đi vào hôm "
                 "qua buổi chiều' hay 'xe máy đi ra từ 8h đến 11h'. Trả về cả phần hệ "
                 "thống đã hiểu được từ câu hỏi, dùng phần đó để giải thích lại cho "
                 "người dùng biết kết quả được lọc theo tiêu chí nào.",
        "tham_so": {
            "type": "object",
            "properties": {
                "cau_hoi": {"type": "string",
                            "description": "Câu tiếng Việt có dấu. Không dấu sẽ hiểu sai."},
                "camera_id": {"type": "string", "description": "Giới hạn trong một camera."},
                "gioi_han": {"type": "integer", "default": 20,
                             "description": "Số kết quả tối đa, không quá 100."},
            },
            "required": ["cau_hoi"],
        },
    },
    "tom_tat_he_thong": {
        "ham": _tom_tat_he_thong,
        "mo_ta": "Số liệu tổng quan: bao nhiêu camera, bao nhiêu pipeline, bao nhiêu "
                 "đang chạy, bao nhiêu sự kiện trong 24 giờ. Dùng để mở đầu khi người "
                 "dùng hỏi chung chung về tình hình hệ thống.",
        "tham_so": {"type": "object", "properties": {}, "required": []},
    },
}


class GoiCongCu(BaseModel):
    ten: str = Field(description="Tên công cụ lấy từ /api/ai/tools")
    tham_so: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools")
def danh_sach_cong_cu(dinh_dang: str = "anthropic"):
    """Bộ mô tả công cụ cho trợ lý AI.

    Hai định dạng phổ biến chỉ khác nhau ở cách đặt tên khoá, nội dung như nhau:
    `anthropic` dùng `input_schema`, `openai` bọc thêm một lớp `function`.
    """
    if dinh_dang not in ("anthropic", "openai"):
        raise HTTPException(422, "dinh_dang phải là 'anthropic' hoặc 'openai'")
    ra = []
    for ten, c in CONG_CU.items():
        if dinh_dang == "anthropic":
            ra.append({"name": ten, "description": c["mo_ta"], "input_schema": c["tham_so"]})
        else:
            ra.append({"type": "function", "function": {
                "name": ten, "description": c["mo_ta"], "parameters": c["tham_so"]}})
    return {"dinh_dang": dinh_dang, "so_cong_cu": len(ra), "cong_cu": ra}


@router.post("/call")
def goi_cong_cu(payload: GoiCongCu):
    """Thực thi một lời gọi công cụ và trả về kết quả.

    Lỗi được trả về trong thân phản hồi thay vì ném mã HTTP 500, vì phía gọi là mô hình
    ngôn ngữ: nó cần đọc được thông báo lỗi để thử lại cho đúng, chứ một mã lỗi trần
    không nói lên điều gì.
    """
    c = CONG_CU.get(payload.ten)
    if c is None:
        return {"thanh_cong": False,
                "loi": f"Không có công cụ tên '{payload.ten}'. "
                       f"Các công cụ hiện có: {', '.join(CONG_CU)}"}
    ham: Callable = c["ham"]
    cho_phep = set((c["tham_so"].get("properties") or {}).keys())
    thua = set(payload.tham_so) - cho_phep
    if thua:
        return {"thanh_cong": False,
                "loi": f"Tham số không hợp lệ: {', '.join(sorted(thua))}. "
                       f"Công cụ này nhận: {', '.join(sorted(cho_phep)) or 'không tham số nào'}"}
    thieu = set(c["tham_so"].get("required") or []) - set(payload.tham_so)
    if thieu:
        return {"thanh_cong": False, "loi": f"Thiếu tham số bắt buộc: {', '.join(sorted(thieu))}"}
    try:
        return {"thanh_cong": True, "ket_qua": ham(**payload.tham_so)}
    except Exception as e:                                    # noqa: BLE001
        return {"thanh_cong": False, "loi": f"{type(e).__name__}: {e}"}
