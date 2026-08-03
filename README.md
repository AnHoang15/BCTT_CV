# VisionOS — Hệ thống giám sát camera bằng thị giác máy tính

Sản phẩm thực tập: nhận diện và **đếm người ra vào** qua vạch, xem camera trực tiếp, xem lại và tìm kiếm sự kiện bằng câu tiếng Việt.

```
BCTT/
├── backend/     FastAPI + YOLOv8 + ByteTrack + LocateAnything-3B + SQLite
├── frontend/    React + TypeScript + Vite + Tailwind
├── report/      Khung báo cáo LaTeX theo hướng dẫn của Khoa
├── scripts/     Script đo thực nghiệm cho Chương 3 của báo cáo
└── videos/      Video mẫu để chạy thử không cần camera
```

## Hai bài toán

| Bài toán | Hình vẽ | Kết quả |
|---|---|---|
| **Đếm đối tượng** | vạch thẳng bất kỳ, kể cả chéo | số lượt Vào và Ra, kèm ảnh từng lượt |
| | đa giác nhiều đỉnh | số đang ở trong vùng + tổng lượt đã bước vào |
| **Nhận diện đối tượng** | không cần | hộp giới hạn và mã định danh |

Đếm qua vạch và đếm trong vùng là **một lựa chọn duy nhất** ở giao diện — kiểu hình bạn vẽ quyết định cách đếm. Chuyển qua lại bằng công tắc *Vẽ vạch / Vẽ vùng* ngay trên khung hình.

Không có hình dựng sẵn: phải tự vẽ thì mới đi tiếp được. Kéo chuột để vẽ vạch theo hướng bất kỳ, hoặc bấm lần lượt để thêm từng đỉnh của đa giác rồi kéo đỉnh để chỉnh. Toạ độ lưu ở dạng chuẩn hoá 0..1 nên vẫn đúng khi camera đổi độ phân giải.

Cả hai bộ đếm đều lấy **điểm neo là bàn chân**: người đứng sát mép vùng có hộp phủ lên vùng nhưng chân còn ở ngoài thì chưa tính là đã vào.

## Tham số cấu hình cho mỗi pipeline

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| **Hướng đếm** | Đếm cả hai chiều, chỉ vào, hoặc chỉ ra | cả hai |
| **Cảnh báo vượt ngưỡng** | Sinh sự kiện khi số đối tượng vượt mức đặt; có khoảng nghỉ 60 giây giữa hai lần báo | tắt |
| **Tự đặt lại số đếm** | Đưa số đếm về 0 mỗi đầu giờ hoặc đầu ngày | không |
| **Tốc độ xử lý** | Ba mức đánh đổi giữa tài nguyên máy và độ nhạy | Cân bằng (15 FPS, tin cậy 25%) |
| **Nhịp xử lý, ngưỡng tin cậy** | Chỉnh tay trong mục *Tuỳ chỉnh nâng cao* | theo preset |
| **Lịch chạy** | Giới hạn AI chỉ chạy trong các khung giờ đã khai báo, nhiều khung ghép được | liên tục 24/7 |

Ba tham số đầu chỉ có ở chế độ **Tiêu chuẩn**. Chế độ Thông minh lấy chiều đếm từ câu mô tả tiếng Việt nên không cần chọn tay.

Ngoài khung giờ chạy, camera vẫn phát hình và vẫn ghi hình — chỉ phần nhận diện tạm nghỉ, khung hình ghi rõ *"Ngoài khung giờ chạy"*. Khung giờ vắt qua nửa đêm (ví dụ 22:00 → 06:00) được xử lý đúng.

Ba mức tốc độ: **Tiết kiệm** 5 FPS / tin cậy 35%, **Cân bằng** 15 FPS / 25%, **Chính xác tối đa** 30 FPS / 20%. Đây là nhịp xử lý thật mà vòng lặp camera giữ, không phải nhãn trang trí — số FPS hiển thị trên khung hình sẽ khớp với mức bạn đặt.

## Hai chế độ hoạt động

| | **Tiêu chuẩn** | **Thông minh** |
|---|---|---|
| Mô hình | YOLOv8 | YOLOv8 đề xuất → LocateAnything-3B lọc |
| Lọc theo | Lớp đối tượng COCO | Mô tả tự do bằng tiếng Việt |
| Ví dụ | đếm mọi người qua vạch | *"người mặc áo đỏ đi vào"* |
| Tốc độ đo được | 45 fps | 18 fps |
| Bộ nhớ | ~1 GB | ~8 GB |

Luồng Thông minh giữ được tốc độ thời gian thực nhờ ba cơ chế: hỏi LA-3B **một lần cho mỗi vết** rồi nhớ theo mã định danh, gọi **bất đồng bộ** trên luồng phụ, và **đệm lượt vượt vạch** trong lúc chờ phán quyết rồi cộng bù khi có kết quả.

## Chạy thử trong 3 phút

**Cửa sổ 1 — backend:**

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python run.py
```

**Cửa sổ 2 — frontend:**

```bash
cd frontend && npm install && npm run dev
```

Mở http://localhost:3000. Tài liệu API ở http://localhost:8000/docs.

Lần chạy đầu, Ultralytics tự tải trọng số `yolov8n.pt` (~6 MB).

## Dùng thử ngay không cần camera

Dự án có sẵn ba video mẫu trong `videos/`:

| Tệp | Cảnh | Ghi chú |
|---|---|---|
| `loi-di-bo.mp4` | lối đi bộ qua đường | người đi cắt ngang khung, đếm rất rõ |
| `subway.mp4` | cửa tàu điện ngầm | người lên xuống qua cửa tàu |
| `people-walking.mp4` | sảnh nhà ga | dòng người dày, hợp thử cảnh đông |

Hai video sau tải từ bộ mẫu của thư viện Supervision. Muốn tải lại:

```bash
cd videos && python -c "from supervision.assets import download_assets, VideoAssets; download_assets(VideoAssets.SUBWAY); download_assets(VideoAssets.PEOPLE_WALKING)"
```

1. Vào **Quản trị → Nguồn camera**, chọn loại nguồn **Tệp video**, dán đường dẫn tuyệt đối tới `videos/loi-di-bo.mp4`
2. Bấm **Kiểm tra kết nối** rồi **Thêm camera** (video được phát lặp vô hạn)
3. Sang **Cấu hình** → chọn camera → *Đếm đối tượng ra/vào* → **Tiêu chuẩn** → kéo vạch **dọc giữa khung** → **Lưu và chạy ngay**
4. Về **Giám sát** xem số đếm chạy; sang **Xem lại** thử gõ *"người đi vào hôm nay"*

Webcam thì điền `0` làm nguồn. Camera IP thì dán chuỗi `rtsp://...`.

## Bật luồng Thông minh

Cần tải mô hình LocateAnything-3B (khoảng 7,3 GB) rồi trỏ biến môi trường tới thư mục đó:

```bash
LA3B_MODEL_DIR=/duong/dan/toi/LocateAnything-3B python run.py
```

Nếu không muốn gõ lại biến môi trường mỗi lần chạy, đặt mô hình vào đúng đường dẫn mặc định là xong. Không cần chép 7,3 GB, một liên kết tượng trưng là đủ:

```bash
mkdir -p backend/models && ln -sfn /duong/dan/toi/LocateAnything-3B backend/models/LocateAnything-3B
```

Chưa có mô hình thì thẻ **Thông minh** trong giao diện tự khoá lại kèm hướng dẫn, phần còn lại của hệ thống vẫn chạy bình thường. Backend kiểm tra thư mục này ở từng lần gọi API chứ không nhớ kết quả, nên thêm mô hình xong chỉ cần tải lại trang, không phải khởi động lại backend.

Nhớ chạy bằng Python trong môi trường ảo, không phải `python3` của hệ thống — thư viện nằm ở đó:

```bash
cd backend && ./.venv/bin/python run.py
```

> ### Chỉ mở ứng dụng ở **một tab** trình duyệt
>
> Đây là giới hạn cần nhớ khi dùng. Mở hai tab cùng lúc thì camera sẽ đen, lúc một ô lúc cả ba, và chuyển qua lại giữa hai tab làm nó đổi liên tục.
>
> Nguyên nhân là trần cứng của HTTP/1.1: mỗi tên miền chỉ được sáu kết nối đồng thời, **tính chung cả trình duyệt chứ không riêng từng tab**. Luồng MJPEG là kết nối sống mãi không đóng, nên ba camera đã chiếm ba chỗ; mở thêm một tab nữa là chạm trần, luồng nào xin sau thì đen.
>
> Một tab với ba, bốn camera thì thoải mái. Cần mở nhiều tab hoặc nhiều camera hơn thì phải đổi lưới sang lấy ảnh làm mới định kỳ thay vì giữ luồng liên tục — mỗi lần lấy ảnh là một yêu cầu ngắn, xong là trả chỗ ngay.

**Về luồng video khi chạy phát triển.** Frontend gọi API qua proxy của Vite ở cổng 3000, nhưng luồng MJPEG thì trỏ thẳng tới backend. Nhờ tách hai tên miền, luồng video và lời gọi API không tranh nhau trần sáu kết nối — trước đây lưới camera làm nghẽn API tới mức giao diện báo máy chủ không phản hồi trong khi máy chủ vẫn trả lời `curl` trong vài mili giây. Địa chỉ luồng bám theo tên máy của trang đang mở nên `localhost`, `127.0.0.1` hay IP nội bộ đều đúng; backend nghe cổng khác thì đặt lại:

```bash
VITE_STREAM_ORIGIN=http://localhost:8001 npm run dev
```

> **Về Apple Silicon.** Backend MPS của PyTorch không an toàn khi nhiều luồng cùng gọi. Mỗi camera chạy YOLO một luồng riêng, LA-3B chạy luồng khác, nên mọi thao tác chạm GPU đều phải đi qua `config.inference_guard()` — kể cả lúc nạp mô hình. Bỏ khoá này thì bật luồng Thông minh là backend chết bằng SIGSEGV trong khoảng một phút, không kịp ghi gì vào nhật ký. Chi tiết ở mục 3.6 của báo cáo.

**Cái giá phải trả về tốc độ.** Chỉ có một GPU, nên trong lúc LA-3B còn vết chưa phán, các camera chạy YOLO tụt từ ~14 xuống ~1,4 khung hình mỗi giây. Hết vết mới thì trở lại 14,2. Đây là giới hạn phần cứng chứ không phải lỗi cấu hình: một mô hình ba tỉ tham số và hai luồng YOLO không cùng lúc chạy đủ nhanh trên một GPU. Máy yếu hoặc nhiều camera thì nên bật luồng Thông minh cho một camera thôi.

Ở bước 2 của trình hướng dẫn, chọn **Thông minh** rồi gõ câu tiếng Việt. Giao diện hiện ngay cách hệ thống hiểu câu đó: phần thuộc tính đã tách, bản dịch tiếng Anh đưa vào LA-3B, và chiều đếm.

| Bạn gõ | Truy vấn đưa vào mô hình | Chiều đếm |
|---|---|---|
| `người đeo ba lô` | `backpack` | cả hai chiều |
| `đếm người mặc áo đỏ đi vào` | `red shirt` | chỉ Vào |
| `người cầm ô đi ra` | `umbrella` | chỉ Ra |
| `người` | — | bỏ qua bộ lọc, chạy như Tiêu chuẩn |

**Vì sao truy vấn chỉ còn vật thể trần?** Đo trên một khung hình 37 người ở sảnh nhà ga:

| Truy vấn | Giữ lại |
|---|---|
| `person` (nền) | 36/37 — 97% |
| `person with backpack` | 32/37 — 86% |
| **`backpack`** | **9/37 — 24%** |
| `person holding umbrella` | 7/37 |
| **`umbrella`** (không ai cầm ô) | **0/37** ✓ |

Câu bắt đầu bằng `person` khiến mô hình bám vào chính chữ đó và gần như bỏ qua vế mô tả. Bỏ chủ ngữ đi thì nó mới thật sự đi tìm vật thể. Đối chiếu bằng mắt: cả 9 khung được giữ với `backpack` đều là người thật sự mang ba lô hoặc túi lớn.

Hệ quả khi dùng: **nêu thẳng vật thể** (“ba lô”, “áo đỏ”, “mũ bảo hiểm”). Mô tả chung chung kiểu “người có mang đồ” sẽ giữ lại gần hết.

## Ba trang chức năng

| Trang | Nội dung |
|---|---|
| **Giám sát** | Danh sách camera bên trái, lưới 1×1 / 2×2 / 3×3 ở giữa, luồng MJPEG đã vẽ sẵn hộp và vạch. **Bấm vào camera** là mở màn hình chi tiết, có nút toàn màn hình; camera đang chạy AI thì kèm **cảnh báo của riêng nó** với ACK và đóng. **Thêm và xoá camera ngay tại đây** |
| **Cấu hình** | Bảng pipeline đã tạo; bấm “Tạo pipeline mới” vào trình hướng dẫn 4 bước (camera → bài toán → luồng & hình vẽ → kiểm tra) |
| **Xem lại** | Trình phát có tua, thanh thời gian 24 giờ, tìm kiếm bằng câu tiếng Việt trả về **lưới ảnh**, bấm ảnh xem lớn hoặc nhảy tới đúng giây |

Giao diện không hiển thị tên mô hình. Người vận hành chỉ thấy “Tiêu chuẩn” và “Thông minh” cùng mô tả việc mỗi chế độ làm được gì; tên mô hình chỉ nằm trong nhật ký hệ thống và tài liệu kỹ thuật.

Các endpoint quản trị (`/api/admin/*`: thời hạn lưu trữ, dung lượng, nhật ký) vẫn còn trong máy chủ và dùng được qua `/docs`, chỉ là không có trang giao diện riêng. Việc dọn dữ liệu quá hạn vẫn chạy tự động sáu giờ một lần.

## Điểm kỹ thuật đáng chú ý

**Đếm bằng điểm neo bàn chân.** Cách đếm theo tâm hộp giới hạn đếm dư khi người đi thẳng vào camera: hộp phình ra thu vào theo nhịp bước, kéo tâm hộp dao động vắt qua vạch. Đo trên `walkback.mp4` (2 người): tâm hộp báo **5 lượt mỗi chiều**, điểm neo bàn chân báo đúng **0** ở vị trí vạch mà không ai thực sự cắt qua. Kèm theo là vùng đệm quanh vạch và yêu cầu giữ phía mới 3 khung hình liên tiếp.

**Ngưỡng ghép vết ByteTrack.** `minimum_matching_threshold` áp lên chi phí `1 - IoU`, không phải lên IoU — chỗ này rất dễ hiểu ngược. Đặt 0,3 tức đòi IoU ≥ 0,7, quá gắt: 2 người sinh ra **65 mã định danh**, vết sống trung vị 2 khung hình. Từ 0,5 trở lên giữ đúng 2 mã suốt 480 khung.

**Nối lại vết theo không gian.** Khi ByteTrack đổi mã do che khuất, mã mới xuất hiện gần vị trí mã vừa mất sẽ kế thừa toàn bộ lịch sử, nên không mất lượt đếm.

**Xem lại có tua được.** Máy chủ xử lý tiêu đề HTTP `Range` và trả mã 206. Thiếu phần này thì thanh tua của trình duyệt bị vô hiệu hoá.

## Chạy lại thực nghiệm

```bash
./backend/.venv/bin/python scripts/exp_anchor.py <video.mp4> 480 0
./backend/.venv/bin/python scripts/exp_bytetrack.py <video.mp4> 480 0
```

Hai script này sinh đúng hai bảng số liệu trong Chương 3 của báo cáo.

## Cấu hình

Đặt qua biến môi trường trước khi chạy `run.py`:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `YOLO_WEIGHTS` | `yolov8n.pt` | Đổi sang `yolov8s/m/l.pt` nếu máy khoẻ |
| `YOLO_IMGSZ` | `960` | Tăng để bắt người ở xa, chậm hơn |
| `YOLO_CONF` | `0.25` | Hạ xuống nếu cảnh đông bị bỏ sót |
| `TARGET_FPS` | `15` | Nhịp xử lý mục tiêu mỗi camera |
| `RECORD_ENABLED` | `1` | Đặt `0` để tắt ghi hình |
| `SEGMENT_SECONDS` | `60` | Độ dài mỗi đoạn video |
| `RETENTION_DAYS` | `7` | Thời hạn lưu trữ |
| `VISIONOS_DEVICE` | tự dò | Ép `cpu`, `cuda` hoặc `mps` |
| `LA3B_MODEL_DIR` | `backend/models/LocateAnything-3B` | Thư mục mô hình cho luồng Thông minh |
| `LA_CROP_SIZE` | `160` | Kích thước khung cắt đưa vào LA-3B |
| `LA_VOTES` | `1` | Hỏi LA-3B nhiều lần rồi lấy đa số; chậm hơn nhưng ổn định hơn |

Hệ thống tự chọn CUDA → MPS → CPU theo thứ tự ưu tiên.

## Giới hạn đã biết

- Luồng Tiêu chuẩn chỉ nhận diện được các lớp có trong bộ dữ liệu COCO (người, xe đạp, ô tô, xe máy, xe buýt, xe tải). Mũ bảo hộ hay sản phẩm lỗi cần huấn luyện riêng.
- **Lọc thuộc tính bằng LA-3B còn nhiễu.** Đo trên một khung hình hai người: `person` giữ 2/2, `person in red shirt` giữ 1/2, `person holding umbrella` giữ 1/2, nhưng `person with backpack` cũng giữ 2/2 dù chỉ nên giữ ít hơn. Khung cắt một người ở độ phân giải thấp và thiếu ngữ cảnh là nguyên nhân chính. Camera đặt góc nghiêng cho kết quả tốt hơn hẳn góc nhìn thẳng từ trên xuống.
- Mô tả nên gõ **có dấu**. Không dấu thì bộ dịch hiểu sai hoàn toàn.
- Một pipeline gắn với đúng một camera. Chọn nhiều camera lúc tạo thì hệ thống sinh ra mỗi camera một pipeline riêng, số đếm tách bạch — không có kiểu cộng dồn số đếm của nhiều camera vào một chỗ.
- Nhiều pipeline trên cùng một camera thì chia nhau một vòng lặp video, nên nhịp xử lý lấy theo pipeline đòi cao nhất. Đặt ba pipeline ở ba mức tốc độ khác nhau thì cả ba đều chạy ở mức cao nhất.
- Chưa có đăng nhập và phân quyền.
- Bản OpenCV cài qua `pip` đôi khi thiếu bộ mã hoá H.264. Chương trình tự lùi về `mp4v` và ghi cảnh báo; khi đó trình duyệt có thể không phát trực tiếp được đoạn ghi, cần chuyển mã bằng `ffmpeg`.
- Kết quả đếm phụ thuộc mạnh vào vị trí vạch. Người đi cắt ngang tầm nhìn cho kết quả ổn định nhất.
