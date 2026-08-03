"""API quản lý camera và luồng video trực tiếp."""
from __future__ import annotations

import anyio
import cv2
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .. import config, db, manager
from ..schemas import CameraIn, CameraUpdate, ProbeIn

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


def _with_runtime(camera: dict) -> dict:
    """Ghép trạng thái tĩnh trong CSDL với trạng thái thực của luồng đang chạy."""
    worker = manager.get(camera["id"])
    state = worker.snapshot_state() if worker else {}
    return {
        **camera,
        "enabled": bool(camera["enabled"]),
        "status": state.get("status", "offline"),
        "fps": state.get("fps", 0),
        "latency_ms": state.get("latency_ms", 0),
        "resolution": (
            f"{state['width']}x{state['height']}"
            if state.get("width") else "—"
        ),
        "in_count": state.get("in_count", 0),
        "out_count": state.get("out_count", 0),
        "occupancy": state.get("occupancy", 0),
        # `pipeline_id`/`pipeline_name` là của pipeline đầu tiên, giữ cho tương thích.
        # `pipelines` mới là danh sách đầy đủ những cái đang chạy trên camera này.
        "pipeline_id": state.get("pipeline_id"),
        "pipeline_name": state.get("pipeline_name"),
        "pipelines": [
            {"id": p["pipeline_id"], "name": p["pipeline_name"],
             "mode": p.get("mode"), "task": p.get("task"),
             "in_count": p.get("in_count", 0), "out_count": p.get("out_count", 0),
             "in_zone": p.get("in_zone", 0), "occupancy": p.get("occupancy", 0)}
            for p in state.get("pipelines", [])
        ],
        "error": state.get("error"),
    }


@router.get("")
def list_cameras():
    return [_with_runtime(c) for c in db.query("SELECT * FROM cameras ORDER BY created_at")]


@router.post("", status_code=201)
def create_camera(payload: CameraIn):
    camera_id = db.new_id()
    db.execute(
        "INSERT INTO cameras (id, name, location, source, kind, enabled, "
        "retention_days, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (camera_id, payload.name, payload.location, payload.source, payload.kind,
         int(payload.enabled), payload.retention_days, db.now()),
    )
    db.log(f"Thêm camera '{payload.name}'", source="api")

    camera = db.query_one("SELECT * FROM cameras WHERE id=?", (camera_id,))
    if payload.enabled:
        manager.start_camera(camera)
    return _with_runtime(camera)


@router.get("/{camera_id}")
def get_camera(camera_id: str):
    camera = db.query_one("SELECT * FROM cameras WHERE id=?", (camera_id,))
    if not camera:
        raise HTTPException(404, "Không tìm thấy camera")
    return _with_runtime(camera)


@router.patch("/{camera_id}")
def update_camera(camera_id: str, payload: CameraUpdate):
    camera = db.query_one("SELECT * FROM cameras WHERE id=?", (camera_id,))
    if not camera:
        raise HTTPException(404, "Không tìm thấy camera")

    fields = payload.model_dump(exclude_none=True)
    if fields:
        if "enabled" in fields:
            fields["enabled"] = int(fields["enabled"])
        assignments = ", ".join(f"{k}=?" for k in fields)
        db.execute(
            f"UPDATE cameras SET {assignments} WHERE id=?",
            (*fields.values(), camera_id),
        )

    updated = db.query_one("SELECT * FROM cameras WHERE id=?", (camera_id,))
    # Đổi nguồn hoặc bật/tắt đều cần khởi động lại luồng đọc.
    if {"source", "enabled", "kind"} & set(fields):
        if updated["enabled"]:
            manager.restart_camera(camera_id)
        else:
            manager.stop_camera(camera_id)
    return _with_runtime(updated)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: str):
    """Xoá camera cùng toàn bộ dữ liệu phát sinh từ nó.

    Phải xoá cả tệp trên đĩa lẫn bản ghi trong cơ sở dữ liệu. Bỏ sót một trong hai sẽ
    để lại đoạn ghi hình mồ côi — trang Xem lại vẫn hiện video của camera đã bị xoá.
    """
    manager.stop_camera(camera_id)
    db.purge_camera_data(camera_id)
    db.execute("DELETE FROM cameras WHERE id=?", (camera_id,))
    db.log(f"Xoá camera {camera_id} và dữ liệu liên quan", source="api")


@router.post("/{camera_id}/toggle")
def toggle_camera(camera_id: str):
    """Bật/tắt luồng video của camera."""
    camera = db.query_one("SELECT * FROM cameras WHERE id=?", (camera_id,))
    if not camera:
        raise HTTPException(404, "Không tìm thấy camera")

    new_state = 0 if camera["enabled"] else 1
    db.execute("UPDATE cameras SET enabled=? WHERE id=?", (new_state, camera_id))
    if new_state:
        manager.start_camera(db.query_one("SELECT * FROM cameras WHERE id=?", (camera_id,)))
    else:
        manager.stop_camera(camera_id)
    return _with_runtime(db.query_one("SELECT * FROM cameras WHERE id=?", (camera_id,)))


@router.post("/probe")
def probe_source(payload: ProbeIn):
    """Kiểm tra nguồn video trước khi lưu — tránh tạo camera chết trong danh sách."""
    return manager.probe(payload.source)


@router.get("/{camera_id}/snapshot")
def snapshot(camera_id: str, raw: bool = False):
    """Một khung hình JPEG. Dùng làm nền để vẽ vạch đếm ở bước cấu hình pipeline.

    `raw=1` trả khung hình chưa vẽ gì lên. Cần thiết khi cấu hình pipeline mới trên
    camera đã có pipeline khác đang chạy: ảnh mặc định đã in sẵn hộp giới hạn, vạch
    đếm và số đếm của pipeline cũ, vẽ vạch mới lên đó thì rối và dễ đặt nhầm chỗ.
    """
    worker = manager.get(camera_id)
    if worker:
        if raw:
            frame = worker.get_source_frame()
            if frame is not None:
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    return Response(buf.tobytes(), media_type="image/jpeg")
        else:
            jpeg = worker.get_jpeg()
            if jpeg:
                return Response(jpeg, media_type="image/jpeg")

    # Luồng chưa chạy: mở nguồn một lần để lấy ảnh.
    camera = db.query_one("SELECT * FROM cameras WHERE id=?", (camera_id,))
    if not camera:
        raise HTTPException(404, "Không tìm thấy camera")

    from ..worker import _parse_source

    cap = cv2.VideoCapture(_parse_source(camera["source"]))
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            raise HTTPException(503, "Camera chưa sẵn sàng")
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return Response(buf.tobytes(), media_type="image/jpeg")
    finally:
        cap.release()


@router.get("/{camera_id}/state")
def camera_state(camera_id: str):
    """Trạng thái thời gian thực: số đếm, FPS, danh sách hộp phát hiện."""
    worker = manager.get(camera_id)
    if not worker:
        raise HTTPException(404, "Camera chưa chạy")
    return worker.snapshot_state()


@router.get("/{camera_id}/stream")
async def stream(request: Request, camera_id: str, raw: bool = False,
                 pipeline_id: str | None = None):
    """Luồng MJPEG (multipart/x-mixed-replace) — hiển thị được bằng thẻ <img>.

    Chọn MJPEG thay vì WebRTC/HLS vì độ trễ thấp, không cần thư viện phía client và
    không cần bước chuyển mã. Đánh đổi là băng thông cao hơn, chấp nhận được trong
    mạng nội bộ với số lượng camera nhỏ.

    `raw=1` phát khung hình chưa vẽ gì, dùng cho ô xem trước lúc cấu hình pipeline
    mới. Khung hình gốc phải nén JPEG ngay tại đây vì worker chỉ nén sẵn bản đã vẽ;
    chi phí đó chỉ phát sinh khi thực sự có người xem luồng gốc.

    `pipeline_id` chọn xem kết quả của đúng một pipeline. Một camera chạy được nhiều
    pipeline cùng lúc; vẽ chồng tất cả lên một khung hình thì rối, nên mỗi pipeline
    giữ bản vẽ riêng và người xem chọn xem cái nào. Không truyền thì lấy bản của
    pipeline đầu tiên.

    Hàm này phải là `async` và phải tự hỏi `request.is_disconnected()`. Bản đồng bộ
    trước đây chỉ dừng khi worker chết, nên mỗi lần người xem đóng tab hay đổi
    pipeline là một kết nối bị bỏ lại vĩnh viễn. Trình duyệt chỉ cho mở sáu kết nối
    tới cùng một máy chủ; rò rỉ vài lần là hết sạch chỗ và mọi lời gọi API bị treo
    hàng đợi cho tới khi hết giờ chờ.
    """
    worker = manager.get(camera_id)
    if not worker:
        raise HTTPException(404, "Camera chưa chạy")

    boundary = "frameboundary"
    # Khung hình riêng của một pipeline cũng ở dạng mảng chưa nén như khung hình gốc,
    # nên đi chung nhánh nén tại chỗ.
    per_frame = raw or pipeline_id is not None

    def encode_current(last_idx):
        """Nén khung hình hiện tại. Chạy ở luồng phụ để không chặn vòng lặp sự kiện."""
        if not per_frame:
            return worker.get_jpeg(), last_idx
        # So sánh theo số thứ tự khung hình: mảng numpy không dùng `is` được như đối
        # tượng bytes đã nén.
        idx = worker.frame_idx
        if idx == last_idx:
            return None, last_idx
        frame = worker.get_source_frame() if raw else worker.get_pipeline_frame(pipeline_id)
        if frame is None:
            return None, last_idx
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return (buf.tobytes() if ok else None), (idx if ok else last_idx)

    async def generate():
        interval = 1.0 / max(1.0, config.TARGET_FPS)
        last_sent = None
        last_idx = None
        while worker.is_alive():
            if await request.is_disconnected():
                return
            jpeg, last_idx = await anyio.to_thread.run_sync(encode_current, last_idx)
            if not per_frame and jpeg is not None and jpeg is last_sent:
                jpeg = None

            if jpeg is not None:
                last_sent = jpeg
                yield (
                    b"--" + boundary.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                    + jpeg + b"\r\n"
                )
            await anyio.sleep(interval)

    return StreamingResponse(
        generate(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-store", "Connection": "close"},
    )
