"""Biến một địa chỉ ảnh chụp thành luồng RTSP.

Nhiều hệ thống camera công cộng — trong đó có hệ thống camera giao thông của Sở Giao
thông TP.HCM — chỉ công bố ảnh JPEG cập nhật liên tục chứ không mở luồng video. OpenCV
không đọc được kiểu nguồn này: `VideoCapture` với một địa chỉ ảnh chỉ lấy đúng một
khung rồi kết thúc.

Chương trình này lấy ảnh theo chu kỳ, ghép thành dòng khung hình rồi đẩy sang máy chủ
RTSP nội bộ. Từ đó camera công cộng dùng được như mọi nguồn RTSP khác, không phải sửa
gì trong `CameraWorker`.

Cần `mediamtx` đang chạy (xem `scripts/rtsp_gia_lap.sh`) hoặc tự khởi động bằng
`--tu-chay`.

    python scripts/cau_noi_anh_chup.py --url "https://.../ImageHandler.ashx?id=..." \\
        --ten camera-giao-thong --fps 2
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request

import cv2
import numpy as np


def lay_anh(url: str, timeout: float = 8.0) -> np.ndarray | None:
    """Tải một ảnh và giải mã. Trả None nếu hỏng, để vòng lặp tự bỏ qua."""
    # Thêm tham số thời gian để phá bộ nhớ đệm. Không có nó, máy chủ trả đúng một ảnh
    # cũ mãi và luồng dựng ra là ảnh tĩnh — kiểm chứng được bằng cách so mã băm hai
    # lần tải liên tiếp.
    ngan = "&" if "?" in url else "?"
    try:
        req = urllib.request.Request(
            f"{url}{ngan}_t={time.time_ns()}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    anh = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return anh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="địa chỉ ảnh chụp")
    ap.add_argument("--ten", required=True, help="tên đường dẫn RTSP")
    ap.add_argument("--fps", type=float, default=2.0,
                    help="số ảnh lấy mỗi giây; nguồn công cộng thường chỉ đổi vài giây một lần")
    ap.add_argument("--cong", type=int, default=8554)
    args = ap.parse_args()

    dau = lay_anh(args.url)
    if dau is None:
        sys.exit(f"Không tải được ảnh từ {args.url}")
    H, W = dau.shape[:2]
    print(f"  nguồn {W}x{H}, đẩy lên rtsp://127.0.0.1:{args.cong}/{args.ten} ở {args.fps} fps")

    # Ghi khung hình thô vào stdin của ffmpeg. Nén H.264 ngay tại đây vì RTSP không
    # truyền được ảnh thô, và `-r` cố định giúp dấu thời gian đều đặn dù mạng trả ảnh
    # lúc nhanh lúc chậm.
    ff = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", str(args.fps), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
         "-pix_fmt", "yuv420p", "-g", str(max(2, int(args.fps * 2))),
         "-f", "rtsp", "-rtsp_transport", "tcp",
         f"rtsp://127.0.0.1:{args.cong}/{args.ten}"],
        stdin=subprocess.PIPE,
    )

    chu_ky = 1.0 / args.fps
    cuoi = dau
    hong = 0
    try:
        while True:
            moc = time.time()
            anh = lay_anh(args.url)
            if anh is None or anh.shape[:2] != (H, W):
                # Giữ nguyên khung cuối thay vì bỏ trống: luồng đứt quãng làm bộ bám
                # vết mất dấu, trong khi khung lặp lại chỉ làm đối tượng đứng yên.
                hong += 1
                anh = cuoi
            else:
                hong = 0
                cuoi = anh
            if hong and hong % 20 == 0:
                print(f"  {hong} lần liên tiếp không lấy được ảnh, vẫn đang thử lại")
            ff.stdin.write(anh.tobytes())
            cho = chu_ky - (time.time() - moc)
            if cho > 0:
                time.sleep(cho)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        if ff.stdin:
            ff.stdin.close()
        ff.wait()


if __name__ == "__main__":
    main()
