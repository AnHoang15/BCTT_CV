"""API cấu hình và điều khiển pipeline AI.

Phạm vi đồ án gồm hai bài toán: `counting` (đếm đối tượng vượt vạch, có tách chiều
Vào/Ra) và `detection` (chỉ nhận diện và hiển thị hộp, không đếm).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from .. import config, db, language, locate_anything, manager
from ..schemas import PipelineIn, PipelineUpdate, PromptPreview

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])

DEFAULT_LINE = {"x1": 0.0, "y1": 0.55, "x2": 1.0, "y2": 0.55}
DEFAULT_ZONE = [
    {"x": 0.25, "y": 0.30}, {"x": 0.75, "y": 0.30},
    {"x": 0.75, "y": 0.80}, {"x": 0.25, "y": 0.80},
]


def _shape(row: dict) -> dict:
    worker = manager.get(row["camera_id"])
    camera_state = worker.snapshot_state() if worker else {}
    # Một camera chạy được nhiều pipeline, nên phải tra đúng phần trạng thái của
    # pipeline này thay vì lấy các trường ở cấp ngoài cùng — chúng là của pipeline
    # đầu tiên và sẽ báo sai số đếm cho những cái còn lại.
    state = next(
        (p for p in camera_state.get("pipelines", []) if p.get("pipeline_id") == row["id"]),
        {},
    )
    is_running = bool(state)
    return {
        **row,
        "classes": json.loads(row["classes"] or '["person"]'),
        "line": json.loads(row["line"]) if row["line"] else DEFAULT_LINE,
        "zone": json.loads(row["zone"]) if row["zone"] else DEFAULT_ZONE,
        "schedule": json.loads(row["schedule"]) if row["schedule"] else None,
        "in_schedule": state.get("in_schedule", True) if is_running else True,
        "schedule_text": state.get("schedule_text") if is_running else None,
        "direction": row["direction"] or "both",
        "auto_reset": row["auto_reset"] or "never",
        "in_zone": state.get("in_zone", 0) if is_running else 0,
        "active": bool(row["active"]),
        "flip": bool(row["flip"]),
        "mode": row["mode"] or "standard",
        "running": is_running,
        "la_calls": state.get("la_calls", 0) if is_running else 0,
        "la_matched": state.get("la_matched", 0) if is_running else 0,
        "la_rejected": state.get("la_rejected", 0) if is_running else 0,
        "la_pending": state.get("la_pending", 0) if is_running else 0,
        "smart_info": state.get("smart_info") if is_running else None,
        "in_count": state.get("in_count", 0) if is_running else 0,
        "out_count": state.get("out_count", 0) if is_running else 0,
        "occupancy": state.get("occupancy", 0) if is_running else 0,
    }


@router.get("")
def list_pipelines(camera_id: str | None = None):
    if camera_id:
        rows = db.query(
            "SELECT * FROM pipelines WHERE camera_id=? ORDER BY created_at DESC",
            (camera_id,),
        )
    else:
        rows = db.query("SELECT * FROM pipelines ORDER BY created_at DESC")
    return [_shape(r) for r in rows]


@router.get("/tasks")
def list_tasks():
    """Danh mục bài toán và lớp đối tượng cho bước chọn ở giao diện."""
    return {
        # Đếm qua vạch và đếm trong vùng gộp thành một lựa chọn: với người dùng đó là
        # cùng một việc "đếm đối tượng", chỉ khác ở hình vẽ. Kiểu hình chọn ở bước vẽ
        # sẽ quyết định thuật toán thật sự chạy bên dưới.
        "tasks": [
            {
                "id": "counting",
                "name": "Đếm đối tượng",
                "description": "Vẽ một vạch để đếm số lượt đi qua theo hai chiều Vào và "
                               "Ra, hoặc khoanh một vùng để đếm số đối tượng đang ở bên "
                               "trong. Mỗi lượt đều có ảnh chụp kèm theo.",
                "needs_shape": True,
                "shapes": ["line", "polygon"],
            },
            {
                "id": "detection",
                "name": "Nhận diện đối tượng",
                "description": "Phát hiện và bám vết đối tượng trong khung hình, hiển thị "
                               "hộp giới hạn và mã định danh. Không đếm.",
                "needs_shape": False,
                "shapes": [],
            },
        ],
        "classes": [
            {"id": name, "name": config.CLASS_LABELS_VI.get(name, name)}
            for name in config.COCO_CLASSES
        ],
        # Mô tả viết cho người vận hành: nói về việc hệ thống làm được gì, không nhắc
        # tên mô hình. Tên mô hình chỉ xuất hiện trong nhật ký và tài liệu kỹ thuật.
        "modes": [
            {
                "id": "standard",
                "name": "Tiêu chuẩn",
                "description": "Đếm tất cả đối tượng thuộc nhóm bạn chọn, ví dụ mọi "
                               "người đi qua vạch. Chạy nhanh, mượt trên máy thông thường.",
                "hint": "Phù hợp khi cần đếm tổng lượng người hoặc xe.",
                "available": True,
            },
            {
                "id": "smart",
                "name": "Thông minh",
                "description": "Bạn mô tả bằng tiếng Việt đối tượng cần đếm, ví dụ "
                               "“người mặc áo đỏ”. Hệ thống chỉ đếm những ai khớp mô tả, "
                               "bỏ qua phần còn lại.",
                "hint": "Chậm hơn và cần máy khoẻ hơn. Dùng khi cần lọc theo đặc điểm "
                        "bên ngoài mà chế độ Tiêu chuẩn không phân biệt được.",
                "available": locate_anything.is_available(),
            },
        ],
        "directions": [
            {"id": "both", "name": "Đếm vào và ra", "description": "Ghi nhận cả hai chiều"},
            {"id": "in", "name": "Chỉ đếm vào", "description": "Bỏ qua lượt đi ra"},
            {"id": "out", "name": "Chỉ đếm ra", "description": "Bỏ qua lượt đi vào"},
        ],
        "auto_resets": [
            {"id": "never", "name": "Không tự đặt lại"},
            {"id": "hourly", "name": "Mỗi đầu giờ"},
            {"id": "daily", "name": "Mỗi đầu ngày"},
        ],
        # Ba mức đánh đổi giữa tài nguyên máy và độ nhạy. Số liệu là nhịp xử lý thật
        # mà vòng lặp camera sẽ giữ, không phải nhãn trang trí.
        "speed_presets": [
            {
                "id": "eco", "name": "Tiết kiệm tài nguyên",
                "description": "Phù hợp server yếu hoặc chạy nhiều camera cùng lúc",
                "target_fps": 5, "conf": 0.35, "recommended": False,
                "bullets": ["Kiểm tra mỗi ~0,2 giây", "Ít tốn CPU và RAM",
                            "Có thể bỏ sót người đi nhanh"],
            },
            {
                "id": "balanced", "name": "Cân bằng",
                "description": "Đề xuất cho hầu hết trường hợp",
                "target_fps": 15, "conf": 0.25, "recommended": True,
                "bullets": ["Phát hiện trong khoảng 0,07 giây", "CPU vừa phải",
                            "Độ chính xác tốt"],
            },
            {
                "id": "accurate", "name": "Chính xác tối đa",
                "description": "Cần máy khoẻ, ít camera",
                "target_fps": 30, "conf": 0.20, "recommended": False,
                "bullets": ["Phát hiện gần như tức thì", "Bám đối tượng mượt hơn",
                            "Tốn CPU hoặc GPU đáng kể"],
            },
        ],
        "trackers": [
            {"id": "bytetrack", "name": "ByteTrack — chính xác, nhanh", "available": True},
        ],
        # Ví dụ chọn theo VẬT THỂ cụ thể. Mô tả càng cụ thể thì lọc càng đúng; nói
        # chung chung kiểu "người có mang đồ" thì hệ thống gần như giữ lại tất cả.
        "prompt_examples": [
            "người đeo ba lô",
            "người mặc áo đỏ đi vào",
            "người cầm ô",
            "người đội mũ bảo hiểm đi ra",
        ],
        "prompt_hint": "Nêu thẳng vật thể hoặc màu áo cần tìm, ví dụ “ba lô”, “áo đỏ”, "
                       "“mũ bảo hiểm”. Mô tả càng cụ thể lọc càng chuẩn; nói chung chung "
                       "thì hệ thống sẽ giữ lại gần hết.",
    }


@router.post("/preview-prompt")
def preview_prompt(payload: PromptPreview):
    """Cho người dùng xem hệ thống hiểu câu lệnh ra sao trước khi chạy pipeline.

    Trả về phần thuộc tính đã tách, bản dịch tiếng Anh đưa vào LA-3B, và chiều đếm.
    """
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(422, "Câu lệnh trống")
    info = language.describe(prompt)
    direction_vi = {"in": "chỉ đếm chiều Vào", "out": "chỉ đếm chiều Ra",
                    "both": "đếm cả hai chiều"}
    return {
        **info,
        "direction_label": direction_vi[info["direction"]],
        "note": (
            "Mô tả này không cần lọc thêm, hệ thống sẽ chạy như chế độ Tiêu chuẩn "
            "cho nhanh."
            if not info["uses_la"] else
            "Mỗi đối tượng chỉ được kiểm tra một lần rồi ghi nhớ kết quả, nên luồng "
            "video vẫn chạy mượt."
        ),
    }


@router.post("", status_code=201)
def create_pipeline(payload: PipelineIn):
    if not db.query_one("SELECT id FROM cameras WHERE id=?", (payload.camera_id,)):
        raise HTTPException(404, "Không tìm thấy camera")
    if not payload.classes:
        raise HTTPException(422, "Phải chọn ít nhất một lớp đối tượng")

    unknown = [c for c in payload.classes if c not in config.COCO_CLASSES]
    if unknown:
        raise HTTPException(422, f"Lớp không hỗ trợ: {', '.join(unknown)}")

    if payload.mode == "smart" and not (payload.prompt or "").strip():
        raise HTTPException(422, "Luồng Thông minh cần một câu mô tả bằng tiếng Việt")

    if payload.task == "zone" and payload.zone is not None and len(payload.zone) < 3:
        raise HTTPException(422, "Vùng đa giác cần ít nhất ba đỉnh")

    pipeline_id = db.new_id()
    line = payload.line.model_dump() if payload.line else DEFAULT_LINE
    zone = [p.model_dump() for p in payload.zone] if payload.zone else DEFAULT_ZONE
    db.execute(
        "INSERT INTO pipelines (id, name, camera_id, task, mode, prompt, classes, "
        "line, zone, flip, conf, direction, max_count, auto_reset, target_fps, "
        "schedule, active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pipeline_id, payload.name, payload.camera_id, payload.task, payload.mode,
         (payload.prompt or "").strip() or None,
         json.dumps(payload.classes), json.dumps(line), json.dumps(zone),
         int(payload.flip), payload.conf, payload.direction, payload.max_count,
         payload.auto_reset, payload.target_fps,
         json.dumps(payload.schedule.model_dump(by_alias=True)) if payload.schedule else None,
         0, db.now()),
    )
    db.log(f"Tạo pipeline '{payload.name}'", source="api")
    return _shape(db.query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,)))


@router.patch("/{pipeline_id}")
def update_pipeline(pipeline_id: str, payload: PipelineUpdate):
    row = db.query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,))
    if not row:
        raise HTTPException(404, "Không tìm thấy pipeline")

    # `exclude_unset` chứ không phải `exclude_none`: chỉ bỏ qua những trường client
    # không gửi. Trường có gửi mà giá trị null là ý muốn xoá — tắt ngưỡng cảnh báo, bỏ
    # lịch chạy, chuyển luồng Thông minh về Tiêu chuẩn. Dùng `exclude_none` thì các thao
    # tác xoá đó im lặng không có tác dụng, giá trị cũ vẫn nằm nguyên trong cơ sở dữ liệu.
    #
    # `by_alias` phải có, giống lúc tạo mới: `ScheduleSlot.from_` mang bí danh `from` vì
    # `from` là từ khoá của Python. Thiếu nó thì lịch chạy lưu xuống với khoá `from_`,
    # trong khi `schedule.py` đọc thẳng `slot["from"]`. Hậu quả không phải sai lịch mà là
    # `KeyError` ném ra từ `describe()` ngay trong vòng lặp worker, đủ để giết luồng
    # camera của pipeline vừa sửa.
    fields = payload.model_dump(exclude_unset=True, by_alias=True)
    if "classes" in fields:
        fields["classes"] = json.dumps(fields["classes"])
    if "line" in fields:
        fields["line"] = json.dumps(fields["line"])
    if "zone" in fields:
        fields["zone"] = json.dumps(fields["zone"])
    if "schedule" in fields:
        fields["schedule"] = json.dumps(fields["schedule"])
    if "flip" in fields:
        fields["flip"] = int(fields["flip"])

    if fields:
        assignments = ", ".join(f"{k}=?" for k in fields)
        db.execute(
            f"UPDATE pipelines SET {assignments} WHERE id=?",
            (*fields.values(), pipeline_id),
        )

    updated = db.query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,))
    # Đang chạy thì nạp lại cấu hình mới ngay, không cần bật/tắt thủ công.
    if updated["active"]:
        manager.attach_pipeline(updated)
    return _shape(updated)


@router.delete("/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str):
    manager.detach_pipeline(pipeline_id)
    db.execute("DELETE FROM pipelines WHERE id=?", (pipeline_id,))


@router.post("/{pipeline_id}/start")
def start_pipeline(pipeline_id: str):
    row = db.query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,))
    if not row:
        raise HTTPException(404, "Không tìm thấy pipeline")

    if row["mode"] == "smart" and not locate_anything.is_available():
        raise HTTPException(
            503,
            "Chế độ Thông minh chưa sẵn sàng trên máy chủ này. Liên hệ quản trị viên "
            "để cài đặt bổ sung, hoặc chuyển pipeline sang chế độ Tiêu chuẩn.",
        )

    if not manager.attach_pipeline(row):
        raise HTTPException(400, "Không khởi động được camera của pipeline")
    return _shape(db.query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,)))


@router.post("/{pipeline_id}/stop")
def stop_pipeline(pipeline_id: str):
    if not db.query_one("SELECT id FROM pipelines WHERE id=?", (pipeline_id,)):
        raise HTTPException(404, "Không tìm thấy pipeline")
    manager.detach_pipeline(pipeline_id)
    return _shape(db.query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,)))


@router.post("/{pipeline_id}/reset")
def reset_pipeline(pipeline_id: str):
    """Đưa số đếm về 0 mà không dừng pipeline."""
    row = db.query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,))
    if not row:
        raise HTTPException(404, "Không tìm thấy pipeline")
    worker = manager.get(row["camera_id"])
    if worker:
        # Chỉ đặt lại pipeline này, không đụng các pipeline khác cùng camera.
        worker.reset_counter(pipeline_id)
    db.log(f"Đặt lại số đếm pipeline '{row['name']}'", source="api")
    return _shape(row)
