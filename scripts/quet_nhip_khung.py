"""Quét nhịp khung hình: hạ nhịp nguồn rồi đo lại độ chính xác đếm.

Báo cáo từng ghi nhận một "vực sâu giữa 10 và 5 fps" (F1 0,80 → 0,50), nhưng phép
đo sinh ra con số đó chạy tay và không được lưu lại thành script nên không kiểm chứng
được. Tệp này dựng lại phép đo cho tái lập được, và mở rộng sang PETS2009 — nguồn duy
nhất trong bộ dữ liệu quay ở nhịp thấp NGUYÊN BẢN (7 fps) chứ không phải bị hạ nhịp
nhân tạo.

Hai điểm phương pháp quan trọng:

1.  Nhãn chuẩn lấy ở NHỊP ĐẦY ĐỦ. Lượt qua vạch là sự kiện vật lý, không phụ thuộc
    việc ta lấy mẫu thưa hay dày. Sinh nhãn từ khung đã lấy mẫu thưa sẽ làm mẫu số
    tự co lại theo, và F1 trông đẹp lên trong khi hệ thống thật sự bỏ sót nhiều hơn.

2.  Chỉ số khung của hệ thống được ánh xạ ngược về đánh số gốc trước khi ghép cặp,
    còn cửa sổ ghép cặp giữ nguyên 1,5 giây theo THỜI GIAN THẬT.

    python scripts/quet_nhip_khung.py --chuoi MOT15-PETS09-S2L1 MOT17-09-FRCNN
"""
from __future__ import annotations

import argparse
import sys
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
    GIAY_GHEP, LECH_DIEM_ANH, _duong_dan, _ghep, _luot_tu_nhan, _nap_nhan,
)

BUOC = [1, 2, 3, 4, 6, 8]


def _phat_hien_buoc(video: Path, buoc: int):
    """Chỉ đưa mỗi khung thứ `buoc` qua bộ phát hiện, đúng như tham số target_fps
    làm trong lúc chạy thật. Trả về cả bản đồ chỉ số khung → khung gốc."""
    cap = cv2.VideoCapture(str(video))
    W, H = int(cap.get(3)), int(cap.get(4))
    fps_goc = cap.get(cv2.CAP_PROP_FPS) or 30.0
    fps_hd = fps_goc / buoc
    det = D.Detector(["person"], conf=config.YOLO_CONF, fps=fps_hd)
    khung, goc_cua = [], []
    i = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % buoc == 0:
            b, ids, nhan, _ = det.track(D.detect(f, det.class_ids, config.YOLO_CONF))
            khung.append((b.copy() if len(b) else b, list(ids), list(nhan)))
            goc_cua.append(i + 1)
        i += 1
    cap.release()
    return khung, goc_cua, W, H, fps_goc, fps_hd


def _chay(khung, goc_cua, p1, p2):
    lc = CentroidCrossingCounter(
        p1, p2, flip=False, directions="both", count_labels={"person"},
        margin_frac=config.COUNTER_MARGIN_FRAC,
    )
    ra = []
    for i, (b, ids, nhan) in enumerate(khung):
        if len(b):
            for e in lc.update(b, ids, nhan, i):
                ra.append((goc_cua[i], e["box"][3], e["direction"]))
    return ra


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chuoi", nargs="*", default=["MOT15-PETS09-S2L1"])
    ap.add_argument("--vach", type=float, default=None,
                    help="vị trí vạch; mặc định quét 4 vị trí rồi lấy trung vị")
    ap.add_argument("--ngang", action="store_true")
    args = ap.parse_args()
    vi_tri = [args.vach] if args.vach else [0.35, 0.45, 0.55, 0.65]

    for chuoi in args.chuoi:
        video, nhan = _duong_dan(chuoi)
        if not video.exists() or not nhan.exists():
            print(f"  bỏ qua {chuoi}: thiếu {video.name} hoặc nhãn")
            continue
        vet = _nap_nhan(nhan)
        print(f"\n══ {chuoi} ══")
        print(f"   {'nhịp':>7s} {'bước':>5s} {'chuẩn':>6s} {'hệ thống':>9s} "
              f"{'khớp':>5s} {'độ phủ':>7s} {'độ chuẩn':>9s} {'F1 TV':>6s}")
        for buoc in BUOC:
            khung, goc_cua, W, H, fps_goc, fps_hd = _phat_hien_buoc(video, buoc)
            lech = max(3, round(GIAY_GHEP * fps_goc))   # theo thời gian thật
            hang = []
            for x in vi_tri:
                if args.ngang:
                    p1, p2 = np.array([0.0, x * H]), np.array([float(W), x * H])
                else:
                    p1, p2 = np.array([x * W, 0.0]), np.array([x * W, float(H)])
                nc = _luot_tu_nhan(vet, p1, p2)
                ht = _chay(khung, goc_cua, p1, p2)
                k, thua, sot = _ghep(ht, nc, lech)
                P = k / len(ht) if ht else 0.0
                R = k / len(nc) if nc else 0.0
                hang.append((len(nc), len(ht), k, R, P,
                             2 * P * R / (P + R) if P + R else 0.0))
            a = np.array(hang, dtype=float)
            print(f"   {fps_hd:>6.1f}f {buoc:>5d} {a[:,0].sum():>6.0f} {a[:,1].sum():>9.0f} "
                  f"{a[:,2].sum():>5.0f} {np.median(a[:,3])*100:>6.0f}% "
                  f"{np.median(a[:,4])*100:>8.0f}% {np.median(a[:,5]):>6.2f}")


if __name__ == "__main__":
    main()
