"""Đo độ chính xác của bộ đếm qua vạch bằng nhãn chuẩn MOT17.

Các phép kiểm trước đây chỉ đối chiếu bằng mắt trên vài vết, nên chỉ trả lời được
"có sai ở chỗ này không" chứ không cho ra con số. MOT17 là bộ dữ liệu bám vết công
khai, mỗi khung hình có sẵn hộp giới hạn và mã vết do người gán, nên tính được số
lượt qua vạch đúng và so trực tiếp với số hệ thống đếm ra.

Cách so: sinh danh sách lượt qua vạch từ nhãn chuẩn bằng **đúng công thức khoảng cách
có dấu và vùng đệm mà bộ đếm dùng**, rồi ghép từng lượt của hệ thống với lượt gần nhất
trong nhãn chuẩn (cùng chiều, lệch dưới 45 khung hình và 200 điểm ảnh). Ghép được là
đúng, không ghép được là đếm thừa, còn dư trong nhãn chuẩn là bỏ sót.

Dùng chung công thức là điều bắt buộc: lần chạy đầu tiên tôi tự viết lại phép tính
chiều theo quy ước riêng, và với vạch dọc thì dấu bị ngược so với bộ đếm — mọi lượt
đều lệch chiều nên không ghép được cặp nào, ra độ chính xác 27% trong khi tổng số lượt
hai bên chỉ chênh nhau đúng một.

    python scripts/danh_gia_mot17.py                 # quét vài vị trí vạch dọc
    python scripts/danh_gia_mot17.py --vach 0.45     # đo đúng một vị trí
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "backend"))

from app import config                              # noqa: E402
from app import detector as D                       # noqa: E402
from app.counter import CentroidCrossingCounter     # noqa: E402

# Chỉ các chuỗi camera TĨNH mới dùng được. MOT17 còn có 05, 10, 11, 13 quay bằng máy
# cầm tay di chuyển — với chúng thì vạch đếm trôi theo khung hình nên bài toán đếm qua
# vạch không định nghĩa được.
#
# Ba nguồn bổ sung nhau: MOT17 cảnh phố thưa--vừa, MOT20 cảnh rất đông, CAVIAR cảnh
# cửa hàng thưa người --- đúng bài toán đếm người ra vào cửa mà hệ thống nhắm tới.
CHUOI_TINH = ["MOT17-02-FRCNN", "MOT17-04-FRCNN", "MOT17-09-FRCNN",
              "MOT20-02", "MOT20-05",
              "CAVIAR-WalkByShop1cor", "CAVIAR-EnterExitCrossingPaths1cor",
              "CAVIAR-OneLeaveShopReenter1cor",
              "MOT15-PETS09-S2L1"]

# Cửa sổ ghép cặp tính theo THỜI GIAN, không theo số khung hình. 1,5 giây là đủ rộng
# cho độ trễ xác nhận của bộ đếm và đủ hẹp để không ghép nhầm hai người đi qua liên
# tiếp. Ghim cứng 45 khung như bản trước chỉ đúng ở 30 fps: PETS2009 quay 7 fps, ở đó
# 45 khung là 6,4 giây — đủ để ghép bừa hai lượt khác nhau và thổi F1 lên một cách giả
# tạo.
GIAY_GHEP = 1.5
LECH_DIEM_ANH = 200


def _duong_dan(chuoi: str) -> tuple[Path, Path]:
    """Đường dẫn video và tệp nhãn của một chuỗi."""
    if chuoi.startswith("CAVIAR-"):
        ten = chuoi[len("CAVIAR-"):]
        return GOC / "videos" / f"caviar-{ten.replace('cor','').lower()}.mp4", \
            GOC / "datasets" / "CAVIAR" / ten / "gt.xml"
    if chuoi.startswith("MOT15-"):
        ten = chuoi[len("MOT15-"):]
        return GOC / "videos" / f"{ten.lower()}.mp4", \
            GOC / "datasets" / "MOT15" / ten / "gt" / "gt.txt"
    bo = "MOT20" if chuoi.startswith("MOT20") else "MOT17"
    so = chuoi.split("-")[1]
    return GOC / "videos" / f"{bo.lower()}-{so}.mp4", \
        GOC / "datasets" / bo / chuoi / "gt" / "gt.txt"


def _nap_nhan_caviar(nhan: Path) -> dict[int, list[tuple]]:
    """Đọc nhãn CAVIAR dạng XML (chuẩn CVML).

    Thứ tự thuộc tính trong thẻ `box` KHÔNG cố định giữa các tệp — có tệp ghi
    `h w xc yc`, tệp khác ghi `xc yc w h`. Vì vậy phải lấy theo tên thuộc tính; ghim
    cứng thứ tự thì tệp thứ hai trả về 0 đối tượng mà không báo lỗi nào, chỉ hiện
    thành `nan` ở cuối bảng.
    """
    import re
    t = nhan.read_text(errors="ignore")
    vet = defaultdict(list)
    for m in re.finditer(r'<frame number="(\d+)">(.*?)</frame>', t, re.S):
        f = int(m.group(1))
        for o in re.finditer(r'<object id="(\d+)">(.*?)</object>', m.group(2), re.S):
            bb = re.search(r"<box\s+([^/>]+)/>", o.group(2))
            if not bb:
                continue
            a = dict(re.findall(r'(\w+)="([\d.\-]+)"', bb.group(1)))
            if not {"xc", "yc", "w", "h"} <= a.keys():
                continue
            xc, yc, h = float(a["xc"]), float(a["yc"]), float(a["h"])
            vet[int(o.group(1))].append((f, xc, yc + h / 2, h))
    return vet


def _nap_nhan(nhan: Path) -> dict[int, list[tuple]]:
    """Chỉ lấy lớp 1 (người đi bộ) với cờ xét = 1.

    MOT17 còn gán nhãn người tĩnh, người trên xe, hình phản chiếu trong tủ kính và
    vùng che khuất, nhưng đặt cờ xét = 0 vì chúng nằm ngoài phạm vi đánh giá.

    MOT15 (PETS2009) dùng ĐỊNH DẠNG KHÁC dù cùng đuôi .txt và cùng sáu cột đầu:

        MOT17:  khung, vết, x, y, rộng, cao, cờ_xét, lớp, độ_nhìn_thấy   (9 cột)
        MOT15:  khung, vết, x, y, rộng, cao, cờ_xét, X, Y, Z             (10 cột)

    Ba cột cuối của MOT15 là toạ độ thế giới thực (thường âm hoặc -1), không phải lớp
    và độ nhìn thấy. Đọc theo luật MOT17 thì `int(p[7])` gặp chuỗi "-4.1554" và ném
    ValueError — may là hỏng to tiếng chứ không âm thầm trả về 0 vết như lỗi CAVIAR
    trước đây. Phân biệt bằng SỐ CỘT, không đoán theo tên tệp.
    """
    if nhan.suffix == ".xml":
        return _nap_nhan_caviar(nhan)
    vet = defaultdict(list)
    for dong in nhan.read_text().splitlines():
        p = dong.split(",")
        if len(p) < 7:
            continue
        if int(float(p[6])) != 1:          # cờ xét, chung cho cả hai định dạng
            continue
        if len(p) == 9 and int(float(p[7])) != 1:   # MOT17/MOT20: lọc thêm theo lớp
            continue
        f, i = int(p[0]), int(p[1])
        x, y, w, h = map(float, p[2:6])
        vet[i].append((f, x + w / 2, y + h, h))
    return vet


def _luot_tu_nhan(vet, p1, p2) -> list[tuple]:
    """Sinh danh sách lượt qua vạch từ nhãn chuẩn, dùng ĐÚNG luật của bộ đếm.

    Kể cả điều kiện hình chiếu nằm trong phạm vi ĐOẠN vạch. Bản đầu bỏ điều kiện này
    nên nhãn chuẩn tính theo đường thẳng vô hạn còn bộ đếm tính theo đoạn hữu hạn: với
    vạch kéo hết cạnh khung hai cách cho kết quả như nhau, nhưng với vạch chỉ dài bằng
    lối đi thì mọi lượt cắt phần kéo dài đều bị tính thành "bỏ sót" trong khi hệ thống
    loại chúng hoàn toàn đúng. Đo trên PETS2009: sai lệch này hạ F1 từ 0,93 xuống 0,79.
    """
    vec = p2 - p1
    dai = float(np.linalg.norm(vec))
    dai_sq = dai * dai
    ra = []
    for _, v in vet.items():
        v.sort()
        phia = None
        for f, cx, cy, bh in v:
            kc = (vec[0] * (cy - p1[1]) - vec[1] * (cx - p1[0])) / dai
            bien = max(4.0, config.COUNTER_MARGIN_FRAC * bh)
            moi = 1 if kc > bien else (-1 if kc < -bien else None)
            if moi is None:
                continue
            if phia is None:
                phia = moi
                continue
            if moi != phia:
                t = ((cx - p1[0]) * vec[0] + (cy - p1[1]) * vec[1]) / dai_sq
                if 0.0 <= t <= 1.0:
                    ra.append((f, cy, "in" if moi == 1 else "out"))
                phia = moi
    return ra


def _chay_he_thong(khung, p1, p2) -> list[tuple]:
    lc = CentroidCrossingCounter(
        p1, p2, flip=False, directions="both", count_labels={"person"},
        margin_frac=config.COUNTER_MARGIN_FRAC,
    )
    ra = []
    for i, (b, ids, nhan) in enumerate(khung):
        if len(b):
            for e in lc.update(b, ids, nhan, i):
                ra.append((i + 1, e["box"][3], e["direction"]))
    return ra


def _ghep(he_thong, nhan_chuan, lech_khung):
    con = list(nhan_chuan)
    thua = []
    for e in he_thong:
        ung = [x for x in con if x[2] == e[2]
               and abs(x[0] - e[0]) < lech_khung
               and abs(x[1] - e[1]) < LECH_DIEM_ANH]
        if ung:
            con.remove(min(ung, key=lambda x: abs(x[0] - e[0])))
        else:
            thua.append(e)
    return len(he_thong) - len(thua), thua, con


def _goc_di_chuyen(khung) -> tuple[float, int]:
    """Góc của hướng di chuyển chính, 0° là đi ngang, 90° là đi dọc theo khung hình.

    Dùng để đoán trước nên vẽ vạch dọc hay ngang: vạch tốt nhất là vạch cắt vuông góc
    với hướng đi. Bỏ các vết quá ngắn hoặc gần như đứng yên vì chúng chỉ đóng góp
    nhiễu chứ không mang thông tin hướng.
    """
    qd = defaultdict(list)
    for _, (b, ids, _n) in enumerate(khung):
        for k, t in enumerate(ids):
            bx = b[k]
            qd[int(t)].append(((bx[0] + bx[2]) / 2, bx[3]))
    vec = []
    for v in qd.values():
        if len(v) < 8:
            continue
        dx, dy = v[-1][0] - v[0][0], v[-1][1] - v[0][1]
        if (dx * dx + dy * dy) ** 0.5 < 20:
            continue
        vec.append((abs(dx), abs(dy)))
    if not vec:
        return float("nan"), 0
    a = np.array(vec)
    return float(np.degrees(np.arctan2(a[:, 1].mean(), a[:, 0].mean()))), len(vec)


def _phat_hien(video: Path, conf: float | None = None):
    """Ngưỡng tin cậy lấy từ cấu hình hệ thống, không chép cứng.

    Đây là lần thứ ba cùng một lỗi trong dự án: chép cứng một tham số đã có sẵn trong
    `config`, rồi sửa `config` mà bảng số liệu vẫn ra giá trị cũ. Hai lần trước là toạ
    độ vạch và hệ số vùng đệm.
    """
    conf = config.YOLO_CONF if conf is None else conf
    cap = cv2.VideoCapture(str(video))
    W, H = int(cap.get(3)), int(cap.get(4))
    # Nhịp khung hình phải lấy từ chính video. ByteTrack quy đổi bộ đệm giữ vết theo
    # nhịp (`max_time_lost = frame_rate/30 * track_buffer`), nên ghim cứng 30 cho một
    # nguồn 7 fps sẽ cho bộ đệm 7,1 giây thay vì 1,6 giây — vết sống dai gấp bốn lần
    # so với lúc hệ thống chạy thật trên nguồn đó.
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    det = D.Detector(["person"], conf=conf, fps=fps)
    khung = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        b, ids, nhan, _ = det.track(D.detect(f, det.class_ids, conf))
        khung.append((b.copy() if len(b) else b, list(ids), list(nhan)))
    cap.release()
    return khung, W, H, float(fps)


def _do_mot_chuoi(chuoi: str, vi_tri, ngang: bool, khung, W, H, vet, lech_khung) -> list[tuple]:
    ra = []
    for x in vi_tri:
        if ngang:
            p1, p2 = np.array([0.0, x * H]), np.array([float(W), x * H])
        else:
            p1, p2 = np.array([x * W, 0.0]), np.array([x * W, float(H)])
        nc = _luot_tu_nhan(vet, p1, p2)
        ht = _chay_he_thong(khung, p1, p2)
        khop, thua, sot = _ghep(ht, nc, lech_khung)
        P = khop / len(ht) if ht else 0.0
        R = khop / len(nc) if nc else 0.0
        F = 2 * P * R / (P + R) if P + R else 0.0
        ra.append((x, len(nc), len(ht), khop, len(thua), len(sot), R, P, F))
    return ra


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chuoi", nargs="*", default=CHUOI_TINH,
                    help="các chuỗi MOT17 cần đo")
    ap.add_argument("--vach", type=float, nargs="*",
                    default=[0.25, 0.35, 0.45, 0.55, 0.65, 0.75],
                    help="vị trí vạch, chuẩn hoá 0–1")
    args = ap.parse_args()

    tom_tat = []
    for chuoi in args.chuoi:
        video, nhan = _duong_dan(chuoi)
        if not video.exists() or not nhan.exists():
            print(f"  bỏ qua {chuoi}: thiếu {video.name} hoặc gt.txt")
            continue
        khung, W, H, fps = _phat_hien(video)
        lech_khung = max(3, round(GIAY_GHEP * fps))
        vet = _nap_nhan(nhan)
        goc, n_vet = _goc_di_chuyen(khung)
        doan = "DỌC" if goc < 30 else ("NGANG" if goc > 60 else "CHÉO")
        print(f"\n══ {chuoi} — {len(khung)} khung {W}x{H} @ {fps:.0f} fps, "
              f"{len(vet)} vết trong nhãn chuẩn ══")
        print(f"   cửa sổ ghép cặp {lech_khung} khung ({GIAY_GHEP} giây)")
        print(f"   góc di chuyển chính {goc:.0f}° trên {n_vet} vết  →  đoán vạch {doan}")

        tot = {}
        for ngang in (False, True):
            kq = _do_mot_chuoi(chuoi, args.vach, ngang, khung, W, H, vet, lech_khung)
            print(f"\n   vạch {'NGANG' if ngang else 'DỌC ':5s} "
                  f"{'chuẩn':>6s} {'hệ thống':>9s} {'khớp':>5s} {'thừa':>5s} {'sót':>4s} "
                  f"{'độ phủ':>7s} {'độ chuẩn':>9s} {'F1':>5s}")
            for x, nnc, nht, k, th, so, R, P, F in kq:
                print(f"   {x:>11.2f} {nnc:>6d} {nht:>9d} {k:>5d} {th:>5d} {so:>4d} "
                      f"{R*100:>6.0f}% {P*100:>8.0f}% {F:>5.2f}")
            tot["ngang" if ngang else "doc"] = max(kq, key=lambda r: r[8])
        thang = "NGANG" if tot["ngang"][8] > tot["doc"][8] else "DỌC"
        print(f"\n   tốt nhất: DỌC F1={tot['doc'][8]:.2f} (x={tot['doc'][0]:.2f})   "
              f"NGANG F1={tot['ngang'][8]:.2f} (y={tot['ngang'][0]:.2f})   "
              f"→ {thang}  {'KHỚP dự đoán' if thang == doan else 'TRÁI dự đoán'}")
        tom_tat.append((chuoi, goc, doan, tot["doc"][8], tot["ngang"][8], thang))

    if len(tom_tat) > 1:
        print(f"\n══ TỔNG HỢP ══")
        print(f"  {'chuỗi':18s} {'góc':>5s} {'đoán':>6s} {'F1 dọc':>7s} {'F1 ngang':>9s} "
              f"{'thực tế':>8s} {'':>6s}")
        for c, g, d, fd, fn, t in tom_tat:
            print(f"  {c:18s} {g:>4.0f}° {d:>6s} {fd:>7.2f} {fn:>9.2f} {t:>8s} "
                  f"{'✓' if t == d else '✗'}")


if __name__ == "__main__":
    main()
