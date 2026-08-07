#!/usr/bin/env bash
# Dựng máy chủ RTSP nội bộ, phát các video mẫu thành luồng camera giả lập.
#
# Không có nguồn RTSP công khai nào dùng được cho kiểm thử: các máy chủ demo kinh điển
# (Wowza, IPVM) đã ngừng hoạt động, còn thứ tìm thấy trên các trang tổng hợp phần lớn là
# camera bị hở cấu hình chứ không phải nguồn được phép dùng. Tự dựng vừa chắc chắn vừa
# tái lập được, lại cho phép chủ động ngắt để thử nhánh kết nối lại của CameraWorker.
#
#   ./scripts/rtsp_gia_lap.sh           # chạy, Ctrl-C để dừng
#   ./scripts/rtsp_gia_lap.sh --liet-ke # chỉ in danh sách URL
set -euo pipefail

GOC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONG="${RTSP_PORT:-8554}"

# tên luồng : tệp video trong thư mục videos/
LUONG=(
  "cong-ra-vao:loi-di-bo.mp4"
  "tau-dien-ngam:subway.mp4"
  "sanh-nha-ga:people-walking.mp4"
  "cua-sanh-ga:cua-ra-vao-sanh-ga.mp4"
  "cua-hang:cua-hang-tien-loi.mp4"
  # Hai chuỗi có nhãn chuẩn: phát qua RTSP thì đối chiếu được số hệ thống đếm với số
  # đúng, tức là kiểm được cả đường RTSP chứ không chỉ kiểm nó có lên hình hay không.
  # PETS2009 quay 7 fps nên còn là ca thử nguồn nhịp thấp.
  "nga-tu-pets:pets09-s2l1.mp4"
  "hanh-lang-caviar:caviar-walkbyshop1.mp4"
)

if [[ "${1:-}" == "--liet-ke" ]]; then
  for m in "${LUONG[@]}"; do echo "rtsp://127.0.0.1:$CONG/${m%%:*}"; done
  exit 0
fi

CAU_HINH="$(mktemp -t mediamtx)"
cat > "$CAU_HINH" <<YAML
logLevel: info
rtspAddress: :$CONG
rtmp: no
hls: no
webrtc: no
srt: no
paths:
YAML

for m in "${LUONG[@]}"; do
  TEN="${m%%:*}"; TEP="${m##*:}"
  # Để mediamtx tự khởi chạy và tự khởi động lại tiến trình phát: một cây tiến trình
  # duy nhất, Ctrl-C là sạch, không còn ffmpeg mồ côi chạy nền.
  #
  # `-re` phát đúng tốc độ thật, `-stream_loop -1` lặp vô hạn, `-c:v copy` khỏi mã hoá
  # lại nên gần như không tốn CPU — phần CPU để dành cho suy luận.
  #
  # `h264_mp4toannexb` là bắt buộc: trong MP4, SPS/PPS nằm riêng ở phần mô tả (dạng
  # AVCC), còn RTSP cần chúng nằm ngay trong dòng bit (dạng Annex-B).
  cat >> "$CAU_HINH" <<YAML
  $TEN:
    runOnInit: >
      ffmpeg -hide_banner -loglevel error -re -stream_loop -1
      -i "$GOC/videos/$TEP" -an -c:v copy -bsf:v h264_mp4toannexb
      -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:$CONG/\$MTX_PATH
    runOnInitRestart: yes
YAML
done

trap 'rm -f "$CAU_HINH"' EXIT

echo "▶ máy chủ RTSP trên cổng $CONG"
for m in "${LUONG[@]}"; do
  printf '   rtsp://127.0.0.1:%s/%-16s ←  %s\n' "$CONG" "${m%%:*}" "${m##*:}"
done
echo
echo "Dán URL trên vào ô Nguồn khi thêm camera. Ctrl-C để dừng."
exec mediamtx "$CAU_HINH"
