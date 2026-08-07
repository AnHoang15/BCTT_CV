"""So sánh ba mức nhịp xử lý trên cùng một chuỗi có nhãn chuẩn.

Ba mức 30 / 15 / 10 fps là ba giá trị từng được đóng gói thành preset trong giao diện.
Tệp này đo cả HAI vế của đánh đổi, vì chỉ nhìn một vế thì kết luận nào cũng sai:

  * Được gì  — độ phủ, độ chuẩn, F1 so với nhãn chuẩn do người gán.
  * Mất gì   — số khung phải suy luận và tổng thời gian GPU.

Phương pháp giữ đúng như `quet_nhip_khung.py`:

  1. Nhãn chuẩn lấy ở NHỊP ĐẦY ĐỦ. Một lượt qua vạch là sự kiện vật lý, không phụ thuộc
     việc ta lấy mẫu thưa hay dày. Sinh nhãn từ khung đã lấy thưa sẽ làm mẫu số tự co
     theo và F1 trông đẹp lên trong khi hệ thống thật sự bỏ sót nhiều hơn.
  2. Chỉ số khung của hệ thống được ánh xạ ngược về đánh số gốc trước khi ghép cặp.
  3. Cửa sổ ghép cặp tính theo THỜI GIAN THẬT (1,5 giây), không theo số khung.
  4. Nhịp hiệu dụng được truyền cho ByteTrack, vì nó quy đổi bộ đệm giữ vết theo nhịp.

    python scripts/so_sanh_nhip.py
    python scripts/so_sanh_nhip.py --chuoi MOT17-09-FRCNN --fps 30 15 10
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "backend"))
sys.path.insert(0, str(GOC / "scripts"))

from app import config                              # noqa: E402
from app import detector as D                       # noqa: E402
from app.counter import CentroidCrossingCounter     # noqa: E402
from danh_gia_mot17 import (                        # noqa: E402
    GIAY_GHEP, _duong_dan, _ghep, _luot_tu_nhan, _nap_nhan,
)

# Bốn vị trí vạch, lấy trung vị để một vị trí may mắn không kéo lệch kết luận.
VI_TRI = [0.35, 0.45, 0.55, 0.65]


def _chay_o_nhip(video: Path, fps_muon: float):
    """Xử lý video ở nhịp `fps_muon`, trả về kết quả bám vết kèm chi phí đo được."""
    cap = cv2.VideoCapture(str(video))
    W, H = int(cap.get(3)), int(cap.get(4))
    fps_goc = cap.get(cv2.CAP_PROP_FPS) or 30.0
    # Chỉ hạ nhịp được theo bội số nguyên: bỏ mỗi khung thứ `buoc`. Đây đúng là cách
    # `target_fps` làm lúc chạy thật, chứ không phải nội suy ra nhịp bất kỳ.
    buoc = max(1, round(fps_goc / fps_muon))
    fps_thuc = fps_goc / buoc

    det = D.Detector(["person"], conf=config.YOLO_CONF, fps=fps_thuc)
    khung, goc_cua, i = [], [], 0
    t0 = time.perf_counter()
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % buoc == 0:
            b, ids, nhan, _ = det.track(D.detect(f, det.class_ids, config.YOLO_CONF))
            khung.append((b.copy() if len(b) else b, list(ids), list(nhan)))
            goc_cua.append(i + 1)
        i += 1
    giay = time.perf_counter() - t0
    cap.release()
    return dict(khung=khung, goc_cua=goc_cua, W=W, H=H, fps_goc=fps_goc,
                fps_thuc=fps_thuc, buoc=buoc, giay=giay, tong_khung=i)


def _dem(kq, p1, p2):
    lc = CentroidCrossingCounter(
        p1, p2, flip=False, directions="both", count_labels={"person"},
        margin_frac=config.COUNTER_MARGIN_FRAC,
    )
    ra = []
    for i, (b, ids, nhan) in enumerate(kq["khung"]):
        if len(b):
            for e in lc.update(b, ids, nhan, i):
                ra.append((kq["goc_cua"][i], e["box"][3], e["direction"]))
    return ra


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chuoi", nargs="*",
                    default=["MOT17-09-FRCNN", "MOT17-04-FRCNN"])
    ap.add_argument("--fps", type=float, nargs="*", default=[30, 15, 10])
    args = ap.parse_args()

    for chuoi in args.chuoi:
        video, nhan = _duong_dan(chuoi)
        if not (video.exists() and nhan.exists()):
            print(f"  bỏ qua {chuoi}: thiếu {video.name} hoặc nhãn chuẩn")
            continue
        vet = _nap_nhan(nhan)
        print(f"\n══ {chuoi} ══")
        print(f"   {'nhịp':>8s} {'khung':>7s} {'giây':>7s} {'ms/khung':>9s} "
              f"{'chuẩn':>6s} {'hệ thống':>9s} {'khớp':>5s} "
              f"{'độ phủ':>7s} {'độ chuẩn':>9s} {'F1':>6s}")
        moc = None
        for fps_muon in args.fps:
            kq = _chay_o_nhip(video, fps_muon)
            lech = max(3, round(GIAY_GHEP * kq["fps_goc"]))
            hang = []
            for x in VI_TRI:
                p1 = np.array([x * kq["W"], 0.0])
                p2 = np.array([x * kq["W"], float(kq["H"])])
                nc = _luot_tu_nhan(vet, p1, p2)
                ht = _dem(kq, p1, p2)
                k, thua, sot = _ghep(ht, nc, lech)
                P = k / len(ht) if ht else 0.0
                R = k / len(nc) if nc else 0.0
                hang.append((len(nc), len(ht), k, R, P,
                             2 * P * R / (P + R) if P + R else 0.0))
            a = np.array(hang, dtype=float)
            f1 = float(np.median(a[:, 5]))
            if moc is None:
                moc = (f1, len(kq["khung"]), kq["giay"])
            n = len(kq["khung"])
            print(f"   {kq['fps_thuc']:>6.1f}f {n:>7d} {kq['giay']:>7.1f} "
                  f"{kq['giay'] / max(1, n) * 1000:>9.0f} "
                  f"{a[:, 0].sum():>6.0f} {a[:, 1].sum():>9.0f} {a[:, 2].sum():>5.0f} "
                  f"{np.median(a[:, 3]) * 100:>6.0f}% {np.median(a[:, 4]) * 100:>8.0f}% "
                  f"{f1:>6.2f}")
        if moc:
            print(f"   (mốc so sánh là dòng đầu: F1 {moc[0]:.2f}, "
                  f"{moc[1]} khung, {moc[2]:.1f} giây)")


if __name__ == "__main__":
    main()
