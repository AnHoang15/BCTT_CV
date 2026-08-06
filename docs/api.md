# Tài liệu API

> Tệp này **sinh tự động** bằng `scripts/sinh_tai_lieu_api.py`, đừng sửa tay.
> Phần tham số vào lấy từ đặc tả OpenAPI; phần dữ liệu ra lấy bằng cách gọi
> thật từng điểm cuối trên hệ thống đang chạy rồi suy ra kiểu.

Sinh lúc 05/08/2026 17:24 · 40 điểm cuối · gốc `http://localhost:8000`

## Quy ước chung

- Mọi thân yêu cầu và phản hồi đều là JSON mã hoá UTF-8.
- Toạ độ vạch đếm và vùng **chuẩn hoá về 0..1** theo chiều rộng và chiều cao
  khung hình, nên không phụ thuộc độ phân giải camera.
- Mốc thời gian theo ISO 8601 giờ địa phương, ví dụ `2026-08-05T14:30:00`.
- Lỗi trả về mã HTTP tương ứng kèm thân `{"detail": "..."}`.
- Điểm cuối trả về ảnh hoặc video dùng `image/jpeg`, `video/mp4` hoặc
  `multipart/x-mixed-replace` chứ không phải JSON; các mục đó ghi rõ bên dưới.

## Lược đồ dùng chung

### `CameraIn`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `name` | `string` | có | — |
| `source` | `string` | có | — |
| `location` | `string` | — | `""` |
| `kind` | `"usb" | "rtsp" | "file"` | — | `"usb"` |
| `enabled` | `boolean` | — | `true` |
| `retention_days` | `integer | null` | — | — |

### `CameraUpdate`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `name` | `string | null` | — | — |
| `source` | `string | null` | — | — |
| `location` | `string | null` | — | — |
| `kind` | `"usb" | "rtsp" | "file" | null` | — | — |
| `enabled` | `boolean | null` | — | — |
| `retention_days` | `integer | null` | — | — |

### `EventUpdate`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `status` | `"new" | "processing" | "closed" | null` | — | — |
| `note` | `string | null` | — | — |

### `GoiCongCu`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `ten` | `string` | có | — |
| `tham_so` | `object` | — | — |

### `LineSpec`

Toạ độ vạch đếm, chuẩn hoá về 0..1 để không phụ thuộc độ phân giải camera.

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `x1` | `number` | có | — |
| `y1` | `number` | có | — |
| `x2` | `number` | có | — |
| `y2` | `number` | có | — |

### `PipelineIn`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `name` | `string` | có | — |
| `camera_id` | `string` | có | — |
| `task` | `"counting" | "zone" | "detection"` | — | `"counting"` |
| `mode` | `"standard" | "smart"` | — | `"standard"` |
| `prompt` | `string | null` | — | — |
| `classes` | `array<string>` | — | `["person"]` |
| `line` | `LineSpec | null` | — | — |
| `zone` | `array<ZonePoint> | null` | — | — |
| `flip` | `boolean` | — | `false` |
| `conf` | `number | null` | — | — |
| `direction` | `"in" | "out" | "both"` | — | `"both"` |
| `max_count` | `integer | null` | — | — |
| `auto_reset` | `"never" | "hourly" | "daily"` | — | `"never"` |
| `target_fps` | `number | null` | — | — |
| `schedule` | `ScheduleSpec | null` | — | — |

### `PipelineUpdate`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `name` | `string | null` | — | — |
| `task` | `"counting" | "zone" | "detection" | null` | — | — |
| `mode` | `"standard" | "smart" | null` | — | — |
| `prompt` | `string | null` | — | — |
| `classes` | `array<string> | null` | — | — |
| `line` | `LineSpec | null` | — | — |
| `zone` | `array<ZonePoint> | null` | — | — |
| `flip` | `boolean | null` | — | — |
| `conf` | `number | null` | — | — |
| `direction` | `"in" | "out" | "both" | null` | — | — |
| `max_count` | `integer | null` | — | — |
| `auto_reset` | `"never" | "hourly" | "daily" | null` | — | — |
| `target_fps` | `number | null` | — | — |
| `schedule` | `ScheduleSpec | null` | — | — |

### `ProbeIn`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `source` | `string` | có | — |

### `PromptPreview`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `prompt` | `string` | có | — |

### `ScheduleSlot`

Một khung giờ chạy. `days` đánh số 2=thứ Hai ... 8=Chủ nhật.

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `days` | `array<integer>` | có | — |
| `from` | `string` | có | — |
| `to` | `string` | có | — |

### `ScheduleSpec`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `enabled` | `boolean` | — | `false` |
| `slots` | `array<ScheduleSlot>` | — | `[]` |

### `SettingsUpdate`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `retention_days` | `integer | null` | — | — |
| `record_enabled` | `boolean | null` | — | — |
| `yolo_conf` | `number | null` | — | — |
| `target_fps` | `number | null` | — | — |

### `ZonePoint`

| Trường | Kiểu | Bắt buộc | Mặc định |
|---|---|---|---|
| `x` | `number` | có | — |
| `y` | `number` | có | — |

## Tích hợp trợ lý AI

Trợ lý AI không đọc tài liệu này rồi tự suy ra cách gọi; nó cần bộ **mô tả công
cụ** dạng máy đọc được. Hai điểm cuối dưới đây cung cấp đúng thứ đó.

### Luồng gọi

```
1. GET  /api/ai/tools            → lấy danh sách công cụ
2. gửi danh sách đó cho mô hình cùng câu hỏi của người dùng
3. mô hình chọn công cụ và tham số
4. POST /api/ai/call             → thực thi, nhận kết quả
5. gửi kết quả lại cho mô hình  → mô hình diễn đạt thành câu trả lời
```

### Công cụ hiện có

| Tên | Tham số | Dùng khi |
|---|---|---|
| `liet_ke_camera` | — | Liệt kê mọi camera trong hệ thống kèm trạng thái đang chạy hay đã tắt. |
| `liet_ke_pipeline` | `camera_id` | Liệt kê các pipeline AI đã cấu hình, kèm bài toán và nhóm đối tượng mà mỗi pipeline theo dõi. |
| `lay_so_dem` | `pipeline_id`, `camera_id`, `so_gio` | Lấy tổng số lượt Vào và Ra trong N giờ gần nhất. |
| `tim_kiem_su_kien` | `cau_hoi`\*, `camera_id`, `gioi_han` | Tra cứu sự kiện bằng câu tiếng Việt tự nhiên, ví dụ 'người đi vào hôm qua buổi chiều' hay 'xe máy đi ra từ 8h đến 11h'. |
| `tom_tat_he_thong` | — | Số liệu tổng quan: bao nhiêu camera, bao nhiêu pipeline, bao nhiêu đang chạy, bao nhiêu sự kiện trong 24 giờ. |

Tham số đánh dấu `*` là bắt buộc.

### Chỉ đọc, không ghi

Bộ công cụ **chỉ gồm các thao tác đọc**. Trợ lý không thêm, sửa hay xoá được gì.
Đây là quyết định có chủ ý: mô hình ngôn ngữ có thể hiểu sai ý người dùng, mà
hiểu sai một câu hỏi thì chỉ ra câu trả lời sai, còn hiểu sai một lệnh xoá thì
mất dữ liệu. Ai cần thao tác ghi thì gọi thẳng điểm cuối tương ứng.

### Xử lý lỗi

`POST /api/ai/call` **luôn trả về HTTP 200**, kể cả khi lời gọi sai. Trạng thái
nằm ở trường `thanh_cong`, còn `loi` mô tả sai ở đâu và cách sửa:

```json
{"thanh_cong": false,
 "loi": "Tham số không hợp lệ: gio. Công cụ này nhận: camera_id, pipeline_id, so_gio"}
```

Lý do không dùng mã lỗi HTTP: phía gọi là mô hình ngôn ngữ, nó cần **đọc được**
thông báo để thử lại cho đúng. Một mã 422 trần không nói lên điều gì.

### Ví dụ đầy đủ

```python
import anthropic, requests

GOC = "http://localhost:8000"
cong_cu = requests.get(f"{GOC}/api/ai/tools").json()["cong_cu"]

client = anthropic.Anthropic()
tin_nhan = [{"role": "user", "content": "Sáng nay có bao nhiêu người đi qua cổng?"}]

while True:
    tl = client.messages.create(
        model="claude-sonnet-5", max_tokens=1024,
        tools=cong_cu, messages=tin_nhan,
    )
    tin_nhan.append({"role": "assistant", "content": tl.content})
    if tl.stop_reason != "tool_use":
        print(tl.content[0].text)
        break

    ket_qua = []
    for khoi in tl.content:
        if khoi.type != "tool_use":
            continue
        r = requests.post(
            f"{GOC}/api/ai/call",
            json={"ten": khoi.name, "tham_so": khoi.input},
        ).json()
        ket_qua.append({
            "type": "tool_result", "tool_use_id": khoi.id,
            "content": str(r.get("ket_qua") if r["thanh_cong"] else r["loi"]),
            "is_error": not r["thanh_cong"],
        })
    tin_nhan.append({"role": "user", "content": ket_qua})
```

Định dạng OpenAI lấy bằng `GET /api/ai/tools?dinh_dang=openai` — nội dung như
nhau, chỉ khác cách đặt tên khoá.

## Camera

Khai báo nguồn video và theo dõi trạng thái luồng.

### `GET /api/cameras`

**List Cameras**

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `id` | `string` | `"cc35a3663a08"` |
| `name` | `string` | `"Cổng ra vào"` |
| `location` | `string` | `"Lối đi bộ qua đường"` |
| `source` | `string` | `"/Users/builder1/Project/BCTT/videos/loi-di…` |
| `kind` | `string` | `"file"` |
| `enabled` | `boolean` | `true` |
| `retention_days` | `null` | `null` |
| `created_at` | `string` | `"2026-07-29T15:44:56"` |
| `status` | `string` | `"online"` |
| `fps` | `integer | number` | `14.2` |
| `latency_ms` | `integer` | `21` |
| `resolution` | `string` | `"3840x2160"` |
| `in_count` | `integer` | `0` |
| `out_count` | `integer` | `0` |
| `occupancy` | `integer` | `0` |
| `pipeline_id` | `string | null` | `"114d1c208615"` |
| `pipeline_name` | `string | null` | `"Đếm người qua quảng trường — dọc x=0.45"` |
| `pipelines` | `array<{id: string, name: string, mode: string, task: string, in_count: integer, out_count: integer, …}>` | `[{"id": "114d1c208615", "name": "Đếm người …` |
| `error` | `null` | `null` |

_Kiểu gộp từ 11 phần tử trong phản hồi thật._

<details><summary>Ví dụ phản hồi</summary>

```json
{
  "id": "cc35a3663a08",
  "name": "Cổng ra vào",
  "location": "Lối đi bộ qua đường",
  "source": "/Users/builder1/Project/BCTT/videos/loi-di-bo.mp4",
  "kind": "file",
  "enabled": true,
  "retention_days": null,
  "created_at": "2026-07-29T15:44:56",
  "status": "online",
  "fps": 14.2,
  "latency_ms": 21,
  "resolution": "3840x2160",
  "in_count": 0,
  "out_count": 0,
  "occupancy": 0,
  "pipeline_id": null,
  "pipeline_name": null,
  "pipelines": [],
  "error": null
}
```

</details>

### `POST /api/cameras`

**Create Camera**

**Thân yêu cầu** — lược đồ [`CameraIn`](#camerain)

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `POST /api/cameras/probe`

**Probe Source**

Kiểm tra nguồn video trước khi lưu — tránh tạo camera chết trong danh sách.

**Thân yêu cầu** — lược đồ [`ProbeIn`](#probein)

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `DELETE /api/cameras/{camera_id}`

**Delete Camera**

Xoá camera cùng toàn bộ dữ liệu phát sinh từ nó.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | path | `string` | có |

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `GET /api/cameras/{camera_id}`

**Get Camera**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | path | `string` | có |

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `id` | `string` | `"cc35a3663a08"` |
| `name` | `string` | `"Cổng ra vào"` |
| `location` | `string` | `"Lối đi bộ qua đường"` |
| `source` | `string` | `"/Users/builder1/Project/BCTT/videos/loi-di…` |
| `kind` | `string` | `"file"` |
| `enabled` | `boolean` | `true` |
| `retention_days` | `null` | `null` |
| `created_at` | `string` | `"2026-07-29T15:44:56"` |
| `status` | `string` | `"online"` |
| `fps` | `number` | `14.2` |
| `latency_ms` | `integer` | `21` |
| `resolution` | `string` | `"3840x2160"` |
| `in_count` | `integer` | `0` |
| `out_count` | `integer` | `0` |
| `occupancy` | `integer` | `0` |
| `pipeline_id` | `null` | `null` |
| `pipeline_name` | `null` | `null` |
| `pipelines` | `array` | `[]` |
| `error` | `null` | `null` |

<details><summary>Ví dụ phản hồi</summary>

```json
{
  "id": "cc35a3663a08",
  "name": "Cổng ra vào",
  "location": "Lối đi bộ qua đường",
  "source": "/Users/builder1/Project/BCTT/videos/loi-di-bo.mp4",
  "kind": "file",
  "enabled": true,
  "retention_days": null,
  "created_at": "2026-07-29T15:44:56",
  "status": "online",
  "fps": 14.2,
  "latency_ms": 21,
  "resolution": "3840x2160",
  "in_count": 0,
  "out_count": 0,
  "occupancy": 0,
  "pipeline_id": null,
  "pipeline_name": null,
  "pipelines": [],
  "error": null
}
```

</details>

### `PATCH /api/cameras/{camera_id}`

**Update Camera**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | path | `string` | có |

**Thân yêu cầu** — lược đồ [`CameraUpdate`](#cameraupdate)

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `GET /api/cameras/{camera_id}/snapshot`

**Snapshot**

Một khung hình JPEG. Dùng làm nền để vẽ vạch đếm ở bước cấu hình pipeline.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | path | `string` | có |
| `raw` | query | `boolean` | — |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

### `GET /api/cameras/{camera_id}/state`

**Camera State**

Trạng thái thời gian thực: số đếm, FPS, danh sách hộp phát hiện.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | path | `string` | có |

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `pipeline_id` | `null` | `null` |
| `pipeline_name` | `null` | `null` |
| `mode` | `null` | `null` |
| `smart_info` | `null` | `null` |
| `in_schedule` | `boolean` | `true` |
| `schedule_text` | `null` | `null` |
| `in_count` | `integer` | `0` |
| `out_count` | `integer` | `0` |
| `in_zone` | `integer` | `0` |
| `occupancy` | `integer` | `0` |
| `detections` | `array` | `[]` |
| `camera_id` | `string` | `"cc35a3663a08"` |
| `status` | `string` | `"online"` |
| `width` | `integer` | `3840` |
| `height` | `integer` | `2160` |
| `fps` | `number` | `14.2` |
| `latency_ms` | `integer` | `21` |
| `frame_idx` | `integer` | `3342` |
| `error` | `null` | `null` |
| `pipelines` | `array` | `[]` |

<details><summary>Ví dụ phản hồi</summary>

```json
{
  "pipeline_id": null,
  "pipeline_name": null,
  "mode": null,
  "smart_info": null,
  "in_schedule": true,
  "schedule_text": null,
  "in_count": 0,
  "out_count": 0,
  "in_zone": 0,
  "occupancy": 0,
  "detections": [],
  "camera_id": "cc35a3663a08",
  "status": "online",
  "width": 3840,
  "height": 2160,
  "fps": 14.2,
  "latency_ms": 21,
  "frame_idx": 3342,
  "error": null,
  "pipelines": []
}
```

</details>

### `GET /api/cameras/{camera_id}/stream`

**Stream**

Luồng MJPEG (multipart/x-mixed-replace) — hiển thị được bằng thẻ <img>.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | path | `string` | có |
| `raw` | query | `boolean` | — |
| `pipeline_id` | query | `string | null` | — |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

### `POST /api/cameras/{camera_id}/toggle`

**Toggle Camera**

Bật/tắt luồng video của camera.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | path | `string` | có |

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

## Pipeline

Cấu hình bài toán AI chạy trên từng camera.

### `GET /api/pipelines`

**List Pipelines**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | query | `string | null` | — |

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `id` | `string` | `"3c28af0bcbfc"` |
| `name` | `string` | `"Đếm người qua phố — dọc x=0.50"` |
| `camera_id` | `string` | `"b38b7f578852"` |
| `task` | `string` | `"counting"` |
| `classes` | `array<string>` | `["person"]` |
| `line` | `{x1: number, y1: number, x2: number, y2: number}` | `{"x1": 0.5, "y1": 0.0, "x2": 0.5, "y2": 1.0}` |
| `flip` | `boolean` | `false` |
| `conf` | `number | null` | `0.25` |
| `active` | `boolean` | `true` |
| `created_at` | `string` | `"2026-08-05T15:50:50"` |
| `mode` | `string` | `"standard"` |
| `prompt` | `string | null` | `"người đi xe đạp"` |
| `zone` | `array<{x: number, y: number}> | null` | `[{"x": 0.25, "y": 0.3}, {"x": 0.75, "y": 0.…` |
| `direction` | `string` | `"both"` |
| `max_count` | `integer | null` | `2` |
| `auto_reset` | `string` | `"never"` |
| `target_fps` | `number | null` | `15.0` |
| `schedule` | `{enabled: boolean, slots: array<object>} | null` | `{"enabled": true, "slots": [{"days": [2, 3,…` |
| `in_schedule` | `boolean` | `true` |
| `schedule_text` | `string | null` | `"chạy liên tục 24/7"` |
| `in_zone` | `integer` | `0` |
| `running` | `boolean` | `true` |
| `la_calls` | `integer` | `0` |
| `la_matched` | `integer` | `0` |
| `la_rejected` | `integer` | `0` |
| `la_pending` | `integer` | `0` |
| `smart_info` | `null` | `null` |
| `in_count` | `integer` | `0` |
| `out_count` | `integer` | `0` |
| `occupancy` | `integer` | `29` |

_Kiểu gộp từ 17 phần tử trong phản hồi thật._

<details><summary>Ví dụ phản hồi</summary>

```json
{
  "id": "3c28af0bcbfc",
  "name": "Đếm người qua phố — dọc x=0.50",
  "camera_id": "b38b7f578852",
  "task": "counting",
  "classes": [
    "person"
  ],
  "line": {
    "x1": 0.5,
    "y1": 0.0,
    "x2": 0.5,
    "y2": 1.0
  },
  "flip": false,
  "conf": 0.25,
  "active": true,
  "created_at": "2026-08-05T15:50:50",
  "mode": "standard",
  "prompt": null,
  "zone": [
    {
      "x": 0.25,
      "y": 0.3
    },
    {
      "x": 0.75,
      "y": 0.3
    },
    {
      "x": 0.75,
      "y": 0.8
    },
    {
      "x": 0.25,
      "y": 0.8
    }
  ],
  "direction": "both",
  "max_count": null,
  "auto_reset": "never",
  "target_fps": 15.0,
  "schedule": null,
  "in_schedule": true,
  "schedule_text": "chạy liên tục 24/7",
  "in_zone": 0,
  "running": true,
  "la_calls": 0,
  "la_matched": 0,
  "la_rejected": 0,
  "la_pending": 0,
  "smart_info": null,
  "in_count": 0,
  "out_count": 0,
  "occupancy": 29
}
```

</details>

### `POST /api/pipelines`

**Create Pipeline**

**Thân yêu cầu** — lược đồ [`PipelineIn`](#pipelinein)

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `POST /api/pipelines/preview-prompt`

**Preview Prompt**

Cho người dùng xem hệ thống hiểu câu lệnh ra sao trước khi chạy pipeline.

**Thân yêu cầu** — lược đồ [`PromptPreview`](#promptpreview)

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `GET /api/pipelines/tasks`

**List Tasks**

Danh mục bài toán và lớp đối tượng cho bước chọn ở giao diện.

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `tasks` | `array<{id: string, name: string, description: string, needs_shape: boolean, shapes: array<string>}>` | `[{"id": "counting", "name": "Đếm đối tượng"…` |
| `classes` | `array<{id: string, name: string}>` | `[{"id": "person", "name": "Người"}, {"id": …` |
| `modes` | `array<{id: string, name: string, description: string, hint: string, available: boolean}>` | `[{"id": "standard", "name": "Tiêu chuẩn", "…` |
| `directions` | `array<{id: string, name: string, description: string}>` | `[{"id": "both", "name": "Đếm vào và ra", "d…` |
| `auto_resets` | `array<{id: string, name: string}>` | `[{"id": "never", "name": "Không tự đặt lại"…` |
| `speed_presets` | `array<{id: string, name: string, description: string, target_fps: integer, conf: number, recommended: boolean, …}>` | `[{"id": "eco", "name": "Tiết kiệm tài nguyê…` |
| `trackers` | `array<{id: string, name: string, available: boolean}>` | `[{"id": "bytetrack", "name": "ByteTrack — c…` |
| `prompt_examples` | `array<string>` | `["người đeo ba lô", "người mặc áo đỏ đi vào…` |
| `prompt_hint` | `string` | `"Nêu thẳng vật thể hoặc màu áo cần tìm, ví …` |

### `DELETE /api/pipelines/{pipeline_id}`

**Delete Pipeline**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `pipeline_id` | path | `string` | có |

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `PATCH /api/pipelines/{pipeline_id}`

**Update Pipeline**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `pipeline_id` | path | `string` | có |

**Thân yêu cầu** — lược đồ [`PipelineUpdate`](#pipelineupdate)

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `POST /api/pipelines/{pipeline_id}/reset`

**Reset Pipeline**

Đưa số đếm về 0 mà không dừng pipeline.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `pipeline_id` | path | `string` | có |

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `POST /api/pipelines/{pipeline_id}/start`

**Start Pipeline**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `pipeline_id` | path | `string` | có |

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `POST /api/pipelines/{pipeline_id}/stop`

**Stop Pipeline**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `pipeline_id` | path | `string` | có |

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

## Sự kiện và thống kê

Lượt qua vạch, cảnh báo, số đếm theo giờ.

### `GET /api/events`

**List Events**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | query | `string | null` | — |
| `pipeline_id` | query | `string | null` | — |
| `type` | query | `string | null` | — |
| `direction` | query | `string | null` | — |
| `status` | query | `string | null` | — |
| `date_from` | query | `string | null` | — |
| `date_to` | query | `string | null` | — |
| `limit` | query | `integer` | — |

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `id` | `string` | `"91a07db57bc0"` |
| `ts` | `string` | `"2026-08-05T17:24:42"` |
| `camera_id` | `string` | `"2ff6168e4411"` |
| `pipeline_id` | `string` | `"114d1c208615"` |
| `type` | `string` | `"crossing"` |
| `direction` | `string` | `"out"` |
| `label` | `string` | `"person"` |
| `track_id` | `integer` | `2` |
| `snapshot` | `string` | `"2ff6168e4411_20260805_172442_2.jpg"` |
| `message` | `string` | `"Người đi ra (ID #2)"` |
| `status` | `string` | `"new"` |
| `note` | `null` | `null` |
| `handled_at` | `null` | `null` |
| `camera_name` | `string` | `"MOT17-02 — Quảng trường"` |

_Kiểu gộp từ 100 phần tử trong phản hồi thật._

<details><summary>Ví dụ phản hồi</summary>

```json
{
  "id": "91a07db57bc0",
  "ts": "2026-08-05T17:24:42",
  "camera_id": "2ff6168e4411",
  "pipeline_id": "114d1c208615",
  "type": "crossing",
  "direction": "out",
  "label": "person",
  "track_id": 2,
  "snapshot": "2ff6168e4411_20260805_172442_2.jpg",
  "message": "Người đi ra (ID #2)",
  "status": "new",
  "note": null,
  "handled_at": null,
  "camera_name": "MOT17-02 — Quảng trường"
}
```

</details>

### `PATCH /api/events/{event_id}`

**Update Event**

Xác nhận xử lý (ACK) hoặc đóng sự kiện kèm ghi chú.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `event_id` | path | `string` | có |

**Thân yêu cầu** — lược đồ [`EventUpdate`](#eventupdate)

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `GET /api/events/{event_id}/snapshot`

**Event Snapshot**

Ảnh chụp của sự kiện. Truyền `w` để lấy bản thu nhỏ theo chiều rộng.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `event_id` | path | `string` | có |
| `w` | query | `integer` | — |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

## Tìm kiếm

Tra cứu sự kiện bằng câu tiếng Việt.

### `GET /api/search`

**Natural Language Search**

Tìm sự kiện bằng câu tiếng Việt, ví dụ: 'người đi vào hôm qua buổi sáng'.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `q` | query | `string` | có |
| `limit` | query | `integer` | — |
| `camera_id` | query | `string | null` | — |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

## Xem lại

Dòng thời gian và đoạn ghi hình đã lưu.

### `GET /api/playback/at`

**Segment At**

Tìm đoạn ghi hình chứa một mốc thời gian.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | query | `string` | có |
| `ts` | query | `string` | có |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

### `GET /api/playback/dates`

**List Dates**

Những ngày có dữ liệu ghi hình, để đánh dấu trên bộ chọn ngày.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | query | `string` | có |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

### `GET /api/playback/segments`

**List Segments**

Các đoạn ghi hình của một camera trong một ngày.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | query | `string` | có |
| `date` | query | `string | null` | — |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

### `GET /api/playback/segments/{segment_id}/download`

**Segment Download**

Tải đoạn ghi hình về máy, kèm sẵn hộp giới hạn và vạch đếm đã vẽ.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `segment_id` | path | `string` | có |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

### `GET /api/playback/segments/{segment_id}/video`

**Segment Video**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `segment_id` | path | `string` | có |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

### `GET /api/playback/timeline`

**Timeline**

Gộp đoạn ghi hình và sự kiện của một ngày thành dữ liệu cho thanh thời gian.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `camera_id` | query | `string` | có |
| `date` | query | `string | null` | — |

**Trả về** — không phải JSON (ảnh, video hoặc luồng MJPEG).

## Quản trị

Cấu hình hệ thống và dọn dữ liệu.

### `GET /api/admin/logs`

**List Logs**

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `level` | query | `string | null` | — |
| `source` | query | `string | null` | — |
| `limit` | query | `integer` | — |

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `id` | `integer` | `1112` |
| `ts` | `string` | `"2026-08-05T17:20:49"` |
| `level` | `string` | `"info"` |
| `source` | `string` | `"camera:b38b7f578852"` |
| `message` | `string` | `"Kết nối camera MOT17-04 — Phố đêm — 1920x1…` |

_Kiểu gộp từ 200 phần tử trong phản hồi thật._

<details><summary>Ví dụ phản hồi</summary>

```json
{
  "id": 1112,
  "ts": "2026-08-05T17:20:49",
  "level": "info",
  "source": "camera:b38b7f578852",
  "message": "Kết nối camera MOT17-04 — Phố đêm — 1920x1080 @30fps"
}
```

</details>

### `GET /api/admin/settings`

**Get Settings**

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `retention_days` | `string` | `"3"` |
| `record_enabled` | `string` | `"1"` |
| `yolo_conf` | `string` | `"0.25"` |
| `target_fps` | `string` | `"15.0"` |

<details><summary>Ví dụ phản hồi</summary>

```json
{
  "retention_days": "3",
  "record_enabled": "1",
  "yolo_conf": "0.25",
  "target_fps": "15.0"
}
```

</details>

### `PUT /api/admin/settings`

**Update Settings**

**Thân yêu cầu** — lược đồ [`SettingsUpdate`](#settingsupdate)

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `GET /api/admin/storage`

**Storage Usage**

Dung lượng đang dùng và dung lượng còn trống của ổ đĩa chứa dữ liệu.

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `segments_bytes` | `integer` | `49465461761` |
| `snapshots_bytes` | `integer` | `7669309605` |
| `database_bytes` | `integer` | `14163968` |
| `used_bytes` | `integer` | `57148935334` |
| `disk_total_bytes` | `integer` | `245107195904` |
| `disk_free_bytes` | `integer` | `34499555328` |
| `disk_used_percent` | `number` | `85.9` |
| `retention_days` | `integer` | `3` |
| `segment_count` | `integer` | `7465` |
| `snapshot_count` | `integer` | `41183` |

<details><summary>Ví dụ phản hồi</summary>

```json
{
  "segments_bytes": 49465461761,
  "snapshots_bytes": 7669309605,
  "database_bytes": 14163968,
  "used_bytes": 57148935334,
  "disk_total_bytes": 245107195904,
  "disk_free_bytes": 34499555328,
  "disk_used_percent": 85.9,
  "retention_days": 3,
  "segment_count": 7465,
  "snapshot_count": 41183
}
```

</details>

### `POST /api/admin/storage/purge`

**Purge Storage**

Xoá ngay dữ liệu quá thời hạn lưu trữ.

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `GET /api/admin/system`

**System Info**

Thông tin môi trường chạy — hữu ích khi chụp ảnh minh hoạ cho báo cáo.

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `python` | `string` | `"3.12.13"` |
| `platform` | `string` | `"Darwin 25.4.0 (arm64)"` |
| `torch` | `string` | `"2.13.0"` |
| `device` | `string` | `"mps"` |
| `yolo_weights` | `string` | `"yolov8n.pt"` |
| `yolo_imgsz` | `integer` | `960` |
| `workers_running` | `integer` | `8` |
| `data_dir` | `string` | `"/Users/builder1/Project/BCTT/backend/data"` |
| `record_enabled` | `boolean` | `true` |
| `segment_seconds` | `integer` | `60` |

<details><summary>Ví dụ phản hồi</summary>

```json
{
  "python": "3.12.13",
  "platform": "Darwin 25.4.0 (arm64)",
  "torch": "2.13.0",
  "device": "mps",
  "yolo_weights": "yolov8n.pt",
  "yolo_imgsz": 960,
  "workers_running": 8,
  "data_dir": "/Users/builder1/Project/BCTT/backend/data",
  "record_enabled": true,
  "segment_seconds": 60
}
```

</details>

## Trợ lý AI

Bộ mô tả công cụ để trợ lý AI gọi được hệ thống.

### `POST /api/ai/call`

**Goi Cong Cu**

Thực thi một lời gọi công cụ và trả về kết quả.

**Thân yêu cầu** — lược đồ [`GoiCongCu`](#goicongcu)

**Trả về** — xem lược đồ tương ứng ở phần Lược đồ dùng chung; thao tác xoá trả về `204 No Content`.

### `GET /api/ai/tools`

**Danh Sach Cong Cu**

Bộ mô tả công cụ cho trợ lý AI.

**Tham số**

| Tên | Vị trí | Kiểu | Bắt buộc |
|---|---|---|---|
| `dinh_dang` | query | `string` | — |

**Trả về**

| Trường | Kiểu | Ví dụ |
|---|---|---|
| `dinh_dang` | `string` | `"anthropic"` |
| `so_cong_cu` | `integer` | `5` |
| `cong_cu` | `array<{name: string, description: string, input_schema: object}>` | `[{"name": "liet_ke_camera", "description": …` |
