# Tài liệu API — VisionOS

*Sinh tự động bằng `scripts/sinh_tai_lieu_api.py` lúc 06/08/2026 09:26 · 40 điểm cuối · gốc `http://localhost:8000` · **đừng sửa tay***

JSON UTF-8. Thời gian ISO 8601 giờ địa phương (`2026-08-06T14:30:00`). Toạ độ vạch và vùng chuẩn hoá 0..1 theo kích thước khung hình. Lỗi trả mã HTTP tương ứng kèm `{"detail": "…"}`.

## Đối tượng trả về

### Camera

| Trường | Kiểu |
|---|---|
| `id` | `str` |
| `name` | `str` |
| `location` | `str` |
| `source` | `str` |
| `kind` | `str` |
| `enabled` | `bool` |
| `retention_days` | `null` |
| `created_at` | `str` |
| `status` | `str` |
| `fps` | `float \| int` |
| `latency_ms` | `int` |
| `resolution` | `str` |
| `in_count` | `int` |
| `out_count` | `int` |
| `occupancy` | `int` |
| `pipeline_id` | `str \| null` |
| `pipeline_name` | `str \| null` |
| `pipelines` | `[object]` |
| `error` | `null` |

### Pipeline

| Trường | Kiểu |
|---|---|
| `id` | `str` |
| `name` | `str` |
| `camera_id` | `str` |
| `task` | `str` |
| `classes` | `[str]` |
| `line` | `{…}` |
| `flip` | `bool` |
| `conf` | `float \| null` |
| `active` | `bool` |
| `created_at` | `str` |
| `mode` | `str` |
| `prompt` | `str \| null` |
| `zone` | `[object] \| null` |
| `direction` | `str` |
| `max_count` | `int \| null` |
| `auto_reset` | `str` |
| `target_fps` | `float \| null` |
| `schedule` | `{…} \| null` |
| `in_schedule` | `bool` |
| `schedule_text` | `str \| null` |
| `in_zone` | `int` |
| `running` | `bool` |
| `la_calls` | `int` |
| `la_matched` | `int` |
| `la_rejected` | `int` |
| `la_pending` | `int` |
| `smart_info` | `null` |
| `in_count` | `int` |
| `out_count` | `int` |
| `occupancy` | `int` |

### Event

| Trường | Kiểu |
|---|---|
| `id` | `str` |
| `ts` | `str` |
| `camera_id` | `str` |
| `pipeline_id` | `str` |
| `type` | `str` |
| `direction` | `str` |
| `label` | `str` |
| `track_id` | `int` |
| `snapshot` | `str` |
| `message` | `str` |
| `status` | `str` |
| `note` | `null` |
| `handled_at` | `null` |
| `camera_name` | `str` |

## Đối tượng gửi lên

### CameraIn

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `name` | `str` | ✓ |
| `source` | `str` | ✓ |
| `location` | `str` |  |
| `kind` | ``usb` \| `rtsp` \| `file`` |  |
| `enabled` | `bool` |  |
| `retention_days` | `int \| null` |  |

### CameraUpdate

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `name` | `str \| null` |  |
| `source` | `str \| null` |  |
| `location` | `str \| null` |  |
| `kind` | ``usb` \| `rtsp` \| `file` \| null` |  |
| `enabled` | `bool \| null` |  |
| `retention_days` | `int \| null` |  |

### EventUpdate

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `status` | ``new` \| `processing` \| `closed` \| null` |  |
| `note` | `str \| null` |  |

### GoiCongCu

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `ten` | `str` | ✓ |
| `tham_so` | `object` |  |

### LineSpec

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `x1` | `float` | ✓ |
| `y1` | `float` | ✓ |
| `x2` | `float` | ✓ |
| `y2` | `float` | ✓ |

### PipelineIn

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `name` | `str` | ✓ |
| `camera_id` | `str` | ✓ |
| `task` | ``counting` \| `zone` \| `detection`` |  |
| `mode` | ``standard` \| `smart`` |  |
| `prompt` | `str \| null` |  |
| `classes` | `[str]` |  |
| `line` | `LineSpec \| null` |  |
| `zone` | `[ZonePoint] \| null` |  |
| `flip` | `bool` |  |
| `conf` | `float \| null` |  |
| `direction` | ``in` \| `out` \| `both`` |  |
| `max_count` | `int \| null` |  |
| `auto_reset` | ``never` \| `hourly` \| `daily`` |  |
| `target_fps` | `float \| null` |  |
| `schedule` | `ScheduleSpec \| null` |  |

### PipelineUpdate

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `name` | `str \| null` |  |
| `task` | ``counting` \| `zone` \| `detection` \| null` |  |
| `mode` | ``standard` \| `smart` \| null` |  |
| `prompt` | `str \| null` |  |
| `classes` | `[str] \| null` |  |
| `line` | `LineSpec \| null` |  |
| `zone` | `[ZonePoint] \| null` |  |
| `flip` | `bool \| null` |  |
| `conf` | `float \| null` |  |
| `direction` | ``in` \| `out` \| `both` \| null` |  |
| `max_count` | `int \| null` |  |
| `auto_reset` | ``never` \| `hourly` \| `daily` \| null` |  |
| `target_fps` | `float \| null` |  |
| `schedule` | `ScheduleSpec \| null` |  |

### ProbeIn

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `source` | `str` | ✓ |

### PromptPreview

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `prompt` | `str` | ✓ |

### ScheduleSlot

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `days` | `[int]` | ✓ |
| `from` | `str` | ✓ |
| `to` | `str` | ✓ |

### ScheduleSpec

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `enabled` | `bool` |  |
| `slots` | `[ScheduleSlot]` |  |

### SettingsUpdate

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `retention_days` | `int \| null` |  |
| `record_enabled` | `bool \| null` |  |
| `yolo_conf` | `float \| null` |  |
| `target_fps` | `float \| null` |  |

### ZonePoint

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| `x` | `float` | ✓ |
| `y` | `float` | ✓ |

## Điểm cuối

### Camera

| Phương thức | Đường dẫn | Vào | Ra |
|---|---|---|---|
| `GET` | `/api/cameras` | — | `[Camera]` |
| `POST` | `/api/cameras` | body `CameraIn` | `Camera` |
| `POST` | `/api/cameras/probe` | body `ProbeIn` | `{ok, message, width, height, fps, elapsed_ms}` |
| `DELETE` | `/api/cameras/{camera_id}` | `camera_id` | `204` |
| `GET` | `/api/cameras/{camera_id}` | `camera_id` | `{id, name, location, source, kind, …}` |
| `PATCH` | `/api/cameras/{camera_id}` | `camera_id`, body `CameraUpdate` | `Camera` |
| `GET` | `/api/cameras/{camera_id}/snapshot` | `camera_id`, `raw`? | `image/jpeg` |
| `GET` | `/api/cameras/{camera_id}/state` | `camera_id` | `{pipeline_id, pipeline_name, mode, smart_info, in_schedule, …}` |
| `GET` | `/api/cameras/{camera_id}/stream` | `camera_id`, `raw`?, `pipeline_id`? | `multipart/x-mixed-replace` |
| `POST` | `/api/cameras/{camera_id}/toggle` | `camera_id` | `Camera` |

### Pipeline

| Phương thức | Đường dẫn | Vào | Ra |
|---|---|---|---|
| `GET` | `/api/pipelines` | `camera_id`? | `[Pipeline]` |
| `POST` | `/api/pipelines` | body `PipelineIn` | `Pipeline` |
| `POST` | `/api/pipelines/preview-prompt` | body `PromptPreview` | `{prompt, filter_text, query, direction, uses_la, …}` |
| `GET` | `/api/pipelines/tasks` | — | `{tasks, classes, modes, directions, auto_resets, …}` |
| `DELETE` | `/api/pipelines/{pipeline_id}` | `pipeline_id` | `204` |
| `PATCH` | `/api/pipelines/{pipeline_id}` | `pipeline_id`, body `PipelineUpdate` | `Pipeline` |
| `POST` | `/api/pipelines/{pipeline_id}/reset` | `pipeline_id` | `Pipeline` |
| `POST` | `/api/pipelines/{pipeline_id}/start` | `pipeline_id` | `Pipeline` |
| `POST` | `/api/pipelines/{pipeline_id}/stop` | `pipeline_id` | `Pipeline` |

### Sự kiện & thống kê

| Phương thức | Đường dẫn | Vào | Ra |
|---|---|---|---|
| `GET` | `/api/events` | `camera_id`?, `pipeline_id`?, `type`?, `direction`?, `status`?, `date_from`?, `date_to`?, `limit`? | `[Event]` |
| `PATCH` | `/api/events/{event_id}` | `event_id`, body `EventUpdate` | `Event` |
| `GET` | `/api/events/{event_id}/snapshot` | `event_id`, `w`? | `image/jpeg` |

### Tìm kiếm

| Phương thức | Đường dẫn | Vào | Ra |
|---|---|---|---|
| `GET` | `/api/search` | `q`, `limit`?, `camera_id`? | binary |

### Xem lại

| Phương thức | Đường dẫn | Vào | Ra |
|---|---|---|---|
| `GET` | `/api/playback/at` | `camera_id`, `ts` | binary |
| `GET` | `/api/playback/dates` | `camera_id` | binary |
| `GET` | `/api/playback/segments` | `camera_id`, `date`? | binary |
| `GET` | `/api/playback/segments/{segment_id}/download` | `segment_id` | `video/mp4` |
| `GET` | `/api/playback/segments/{segment_id}/video` | `segment_id` | `video/mp4` |
| `GET` | `/api/playback/timeline` | `camera_id`, `date`? | binary |

### Quản trị

| Phương thức | Đường dẫn | Vào | Ra |
|---|---|---|---|
| `GET` | `/api/admin/logs` | `level`?, `source`?, `limit`? | `[{id, ts, level, source, …}]` |
| `GET` | `/api/admin/settings` | — | `{retention_days, record_enabled, yolo_conf, target_fps}` |
| `PUT` | `/api/admin/settings` | body `SettingsUpdate` | object |
| `GET` | `/api/admin/storage` | — | `{segments_bytes, snapshots_bytes, database_bytes, used_bytes, disk_total_bytes, …}` |
| `POST` | `/api/admin/storage/purge` | — | object |
| `GET` | `/api/admin/system` | — | `{python, platform, torch, device, yolo_weights, …}` |

### Trợ lý AI

| Phương thức | Đường dẫn | Vào | Ra |
|---|---|---|---|
| `POST` | `/api/ai/call` | body `GoiCongCu` | object |
| `GET` | `/api/ai/tools` | `dinh_dang`? | `{dinh_dang, so_cong_cu, cong_cu}` |

## Tích hợp trợ lý AI

Trợ lý AI cần bộ mô tả công cụ dạng máy đọc được, không đọc tài liệu này.
`GET /api/ai/tools` trả về bộ đó, `POST /api/ai/call` thực thi một lời gọi.

| Công cụ | Tham số | Dùng khi |
|---|---|---|
| `liet_ke_camera` | — | Liệt kê mọi camera trong hệ thống kèm trạng thái đang chạy hay đã tắt. |
| `liet_ke_pipeline` | `camera_id`? | Liệt kê các pipeline AI đã cấu hình, kèm bài toán và nhóm đối tượng mà mỗi pipeline theo dõi. |
| `lay_so_dem` | `pipeline_id`?, `camera_id`?, `so_gio`? | Lấy tổng số lượt Vào và Ra trong N giờ gần nhất. |
| `tim_kiem_su_kien` | `cau_hoi`, `camera_id`?, `gioi_han`? | Tra cứu sự kiện bằng câu tiếng Việt tự nhiên, ví dụ 'người đi vào hôm qua buổi chiều' hay 'xe máy đi ra từ 8h đến 11h'. |
| `tom_tat_he_thong` | — | Số liệu tổng quan: bao nhiêu camera, bao nhiêu pipeline, bao nhiêu đang chạy, bao nhiêu sự kiện trong 24 giờ. |

`?` = tuỳ chọn. Thêm `?dinh_dang=openai` để lấy định dạng OpenAI.

**Chỉ đọc.** Trợ lý không thêm, sửa hay xoá được gì — hiểu sai một câu hỏi thì
chỉ ra câu trả lời sai, hiểu sai một lệnh xoá thì mất dữ liệu.

**Lỗi luôn trả HTTP 200**, trạng thái ở `thanh_cong`, `loi` nói rõ cách sửa:

```json
{"thanh_cong": false,
 "loi": "Tham số không hợp lệ: gio. Công cụ này nhận: camera_id, pipeline_id, so_gio"}
```

Phía gọi là mô hình ngôn ngữ, nó cần đọc được thông báo để thử lại cho đúng;
một mã 422 trần không nói lên điều gì.

```python
cong_cu = requests.get(f"{GOC}/api/ai/tools").json()["cong_cu"]
tl = client.messages.create(model="claude-sonnet-5", max_tokens=1024,
                            tools=cong_cu, messages=tin_nhan)
# với mỗi khối tool_use trong tl.content:
r = requests.post(f"{GOC}/api/ai/call",
                  json={"ten": khoi.name, "tham_so": khoi.input}).json()
# trả r["ket_qua"] (hoặc r["loi"] kèm is_error) lại cho mô hình
```
