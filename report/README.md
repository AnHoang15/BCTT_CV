# Khung báo cáo thực tập (LaTeX)

Cấu trúc bám theo *HƯỚNG DẪN BÁO CÁO KẾT THÚC THỰC TẬP* của Khoa Toán – Cơ – Tin học.

## Biên dịch

Cần **XeLaTeX** (không dùng pdfLaTeX) vì tài liệu nạp phông hệ thống qua `fontspec`.

```bash
cd report && make
```

Chưa có LaTeX trên máy:

- **macOS**: `brew install --cask mactex` (bản đầy đủ, ~4 GB) hoặc `basictex` rồi cài thêm gói
- **Ubuntu/Debian**: `sudo apt install texlive-full latexmk`
- **Không muốn cài**: tải cả thư mục `report/` lên [Overleaf](https://overleaf.com), vào *Menu → Compiler* chọn **XeLaTeX**

## Bản đồ tệp

| Tệp | Nội dung | Mục trong hướng dẫn của Khoa |
|---|---|---|
| `main.tex` | Cấu hình chung, phông chữ, lề, thứ tự chương | — |
| `chapters/00_bia.tex` | Trang bìa | — |
| `chapters/00_loi_cam_on.tex` | Lời cảm ơn | — |
| `chapters/00_viet_tat.tex` | Danh mục chữ viết tắt | Mục 4 |
| `chapters/01_gioi_thieu.tex` | Bài toán, khảo sát công nghệ, lý do chọn | **Mục 1** (1–2 trang) |
| `chapters/02_trien_khai.tex` | Công việc đã làm theo đề mục | **Mục 2** (không giới hạn) |
| `chapters/03_ket_qua.tex` | Sản phẩm, giao diện, thực nghiệm, kiểm thử | **Mục 3** |
| `chapters/04_phu_luc.tex` | Phân công, hướng dẫn cài đặt, lược đồ CSDL, API | **Mục 4** |
| `chapters/05_nhan_xet.tex` | Mẫu nhận xét của công ty | **Mục 5** (1–2 trang) |
| `refs.bib` | Tài liệu tham khảo | Mục 4 |

## Việc cần làm trước khi in

Mọi chỗ cần điền đều đánh dấu `\todo{...}` và **hiện màu đỏ** trong bản PDF, nên không bỏ sót được.

1. Điền thông tin cá nhân ở `00_bia.tex` và `00_loi_cam_on.tex`
2. Chỉnh mục 1.1 cho khớp bối cảnh công ty thực tập
3. Chụp màn hình ứng dụng, lưu vào `figures/`, bỏ chú thích các dòng `\includegraphics`
4. Sinh hai sơ đồ từ mã PlantUML và DBML trong phụ lục
5. **Chạy lại thực nghiệm trên dữ liệu của bạn** rồi cập nhật số liệu Chương 3
6. Cập nhật cột trạng thái bảng kiểm thử
7. Chọn mẫu nhận xét cá nhân hoặc nhóm ở `05_nhan_xet.tex`, xoá mẫu còn lại
8. Ẩn dấu `\todo` khi nộp: sửa trong `main.tex` thành

   ```latex
   \newcommand{\todo}[1]{}
   ```

## Số liệu thực nghiệm có sẵn

Chương 3 đã điền sẵn số liệu **đo thật** trên Apple M4 / 24 GB / MPS với `yolov8n`:

- Ảnh hưởng của `minimum_matching_threshold`: ngưỡng 0,3 sinh 65 mã ID cho 2 người, độ dài vết trung vị 2 khung; từ 0,5 trở lên giữ đúng 2 mã, vết dài trọn 480 khung
- Điểm neo bàn chân so với tâm hộp: với vạch dọc giữa khung, tâm hộp báo 5 lượt mỗi chiều trong khi cảnh chỉ có 2 người; điểm neo bàn chân cho đúng 0
- Tốc độ: 62,9 fps ở 720×404 và 45,1 fps ở 2160×3840

Đây là số của máy dùng để phát triển. Chạy lại trên máy bạn rồi thay số, đừng chép nguyên — hội đồng thường hỏi cấu hình máy đo.

Hai script dùng để đo nằm ở `../scripts/`.
