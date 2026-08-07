"""Kiểm thử bộ đếm qua vạch trên toàn bộ video mẫu, kèm dựng video output.

Chạy độc lập với backend đang phục vụ: nạp thẳng YOLO + ByteTrack + bộ đếm, phát lại
từng video theo đúng tham số của luồng Tiêu chuẩn rồi ghi ra video đã vẽ chú thích.
Nhờ vậy con số trong báo cáo tái lập được, không phụ thuộc vào đoạn ghi hình nào tình
cờ rơi vào lúc bấm nút.

Kết quả phát hiện được lưu đệm ra `.pkl` vì suy luận YOLO là phần tốn thời gian nhất —
lần chạy sau chỉ còn việc đếm và vẽ, cho phép quét tham số trong vài giây thay vì vài
chục phút.

    python scripts/kiem_thu_dem.py            # chạy đủ, dựng video
    python scripts/kiem_thu_dem.py --quet     # chỉ quét hệ số biên, không dựng video
"""
from __future__ import annotations

import argparse
import json
import pickle
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "backend"))

from app import config                             # noqa: E402
from app import detector as D                      # noqa: E402
from app.counter import CentroidCrossingCounter    # noqa: E402
from app.worker import CLASS_COLORS, DrawStyle     # noqa: E402

DEM = GOC / "output"
DEM_TAM = GOC / ".cache_kiemthu"

API = "http://localhost:8000/api"
DOI_TUONG = ["person"]
NGUONG_TIN_CAY = 0.25

# Chạy hết video. Trước đây giới hạn 900 khung cho nhanh, nhưng nó cắt cụt MOT17-04
# (1050 khung) khiến số đếm trên video output khác số trong bảng đánh giá — mà bảng
# đánh giá lại đọc đủ video. Hai con số cùng tên gọi mà khác nhau thì tệ hơn là chạy
# lâu thêm vài phút.
SO_KHUNG_TOI_DA = 100_000

# ── Chuỗi có nhãn chuẩn ──────────────────────────────────────────────────────
# Các bộ dữ liệu công khai không có pipeline trong hệ thống nên `nap_cac_ca()` không
# thấy chúng. Khai báo ở đây để chúng đi qua ĐÚNG bộ dựng video như mọi ca khác.
# Trước đây mỗi chuỗi được dựng bằng một script rời trong /tmp, kết quả là hai tệp
# output cùng thư mục mà khác định dạng: một tệp dải màu JPEG (yuvj420p) một tệp dải
# màu video (yuv420p), tên tệp thiếu mã pipeline, bảng số vẽ khác kiểu, cỡ chữ khác.
#
# Vạch phải cắt VUÔNG GÓC hướng đi chính và chỉ DÀI BẰNG lối đi thật. Vạch kéo hết
# chiều cao khung hình trông có vẻ "bao trọn" nhưng phần lớn chiều dài của nó nằm trên
# mái nhà và bãi cỏ — đo được ở PETS2009: vạch dọc kéo hết khung chỉ có 62% chiều dài
# nằm trên chỗ người thật sự bước, cắt đúng dải đi bộ thì lên 93%. Phần thừa không
# thay đổi số đếm (bộ đếm đã đòi hình chiếu nằm trong đoạn vạch) nhưng làm người xem
# hiểu sai là hệ thống đang canh cả vùng đó.
CA_BO_DU_LIEU = [
    dict(ten="PETS09-S2L1 — Ngã tư",
         tep="pets09-s2l1.mp4",
         nhan="datasets/MOT15/PETS09-S2L1/gt/gt.txt",
         # Dọc, cắt ngang dải đi bộ y = 0,24--0,56 nơi tập trung toàn bộ lưu lượng.
         vach=(0.45, 0.24, 0.45, 0.56), lat=False),
    dict(ten="CAVIAR WalkByShop1 — Hành lang cửa hàng",
         tep="caviar-walkbyshop1.mp4",
         nhan="datasets/CAVIAR/WalkByShop1cor/gt.xml",
         # Chéo, vuông góc với trục hành lang.
         vach=(1.000, 0.512, 0.268, 1.000), lat=False),
    dict(ten="CAVIAR WalkByShop1 — vach doc hanh lang (doi chung)",
         tep="caviar-walkbyshop1.mp4",
         nhan="datasets/CAVIAR/WalkByShop1cor/gt.xml",
         # Cùng cảnh, cùng nhãn chuẩn, chỉ khác hướng vạch: vạch này chạy DỌC theo
         # hành lang thay vì cắt ngang. Giữ lại làm đối chứng cho Mục "Hướng vạch
         # quyết định độ ổn định" — một chiều luôn cắt vạch ở phía xa camera, nơi
         # người nhỏ và hay bị bỏ sót, nên sai lệch dồn hết về chiều đó.
         vach=(0.428, 0.202, 0.782, 0.998), lat=False,
         hau_to="_vachdoc"),
]


def nap_ca_bo_du_lieu() -> list[dict]:
    """Dựng danh sách ca từ CA_BO_DU_LIEU, kèm số lượt đúng theo nhãn chuẩn."""
    sys.path.insert(0, str(GOC / "scripts"))
    from danh_gia_mot17 import _luot_tu_nhan, _nap_nhan

    cac_ca = []
    for m in CA_BO_DU_LIEU:
        video, nhan = GOC / "videos" / m["tep"], GOC / m["nhan"]
        if not (video.exists() and nhan.exists()):
            print(f"  bỏ qua {m['ten']}: thiếu {video.name} hoặc nhãn chuẩn")
            continue
        cap = cv2.VideoCapture(str(video))
        W, H = int(cap.get(3)), int(cap.get(4))
        cap.release()
        x1, y1, x2, y2 = m["vach"]
        luot = _luot_tu_nhan(_nap_nhan(nhan),
                             np.array([x1 * W, y1 * H]), np.array([x2 * W, y2 * H]))
        vao = sum(1 for e in luot if e[2] == "in")
        cac_ca.append(dict(m, khoa=Path(m["tep"]).stem + m.get("hau_to", "_nhanchuan"),
                           chuan=(vao, len(luot) - vao),
                           ghi_chu=f"nhãn chuẩn {vao} vào / {len(luot) - vao} ra"))
    return cac_ca


def nap_cac_ca() -> list[dict]:
    """Lấy cấu hình vạch trực tiếp từ các pipeline đang chạy trong hệ thống.

    Trước đây toạ độ vạch được chép cứng vào tệp này. Người dùng vẽ lại vạch trên giao
    diện thì bản chép cứng không đổi theo, và video output dựng ra mang vạch cũ trong
    khi hệ thống đang đếm theo vạch mới — đúng kiểu sai lệch âm thầm, nhìn video không
    thể biết. Đọc thẳng từ API thì chỉ còn một nguồn sự thật.

    Chỉ nhận pipeline đếm qua vạch trên camera có nguồn là tệp trong `videos/`; camera
    RTSP không phát lại được nên không dựng video output tái lập được.
    """
    import urllib.request

    with urllib.request.urlopen(f"{API}/cameras", timeout=10) as r:
        camera = {c["id"]: c for c in json.load(r)}
    with urllib.request.urlopen(f"{API}/pipelines", timeout=10) as r:
        pipeline = json.load(r)

    cac_ca = []
    for p in pipeline:
        cam = camera.get(p["camera_id"])
        if cam is None or p.get("task") != "counting" or not p.get("line"):
            continue
        tep = Path(cam["source"])
        if not (tep.is_file() and tep.parent == GOC / "videos"):
            continue
        v = p["line"]
        cac_ca.append(dict(
            ten=f"{cam['name']} — {p['name']}",
            tep=tep.name,
            # Một camera chạy được nhiều pipeline, mỗi cái một vạch. Tên tệp output phải
            # kèm mã pipeline, không thì cái sau ghi đè cái trước và chỉ còn lại một.
            khoa=f"{tep.stem}_{p['id'][:8]}",
            vach=(v["x1"], v["y1"], v["x2"], v["y2"]),
            lat=bool(p.get("flip")),
            ghi_chu=f"pipeline {p['id'][:8]}, chiều {p.get('direction', 'both')}",
        ))
    if not cac_ca:
        raise SystemExit(
            "Không lấy được pipeline nào từ backend. Kiểm tra backend đã chạy chưa "
            f"({API}), và đã có pipeline đếm qua vạch trên camera dùng tệp video."
        )
    return cac_ca


def _phat_hien(ca: dict) -> dict:
    """Chạy YOLO + ByteTrack một lần rồi lưu đệm."""
    DEM_TAM.mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(GOC / "videos" / ca["tep"]))
    W, H = int(cap.get(3)), int(cap.get(4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    tong = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Nhịp nằm trong tên tệp đệm vì nó đổi hành vi bám vết: ByteTrack quy đổi bộ đệm
    # giữ vết theo nhịp, nên đệm dựng ở nhịp này không dùng lại cho nhịp khác được.
    dem = DEM_TAM / f"{Path(ca['tep']).stem}_fps{int(round(fps))}.pkl"
    if dem.exists():
        cap.release()
        return pickle.load(dem.open("rb"))

    # Ghim cứng 30 cho nguồn 7 fps sẽ cho bộ đệm giữ vết 7,1 giây thay vì 1,6 giây.
    det = D.Detector(DOI_TUONG, conf=NGUONG_TIN_CAY, fps=fps)
    khung = []
    for _ in range(min(tong, SO_KHUNG_TOI_DA)):
        ok, f = cap.read()
        if not ok:
            break
        b, ids, nhan, _ = det.track(D.detect(f, det.class_ids, NGUONG_TIN_CAY))
        khung.append((b.copy() if len(b) else b, list(ids), list(nhan)))
    cap.release()

    data = dict(W=W, H=H, fps=fps, tong=tong, khung=khung)
    pickle.dump(data, dem.open("wb"))
    return data


def _bo_dem(ca: dict, W: int, H: int, bien: float) -> CentroidCrossingCounter:
    x1, y1, x2, y2 = ca["vach"]
    return CentroidCrossingCounter(
        (x1 * W, y1 * H), (x2 * W, y2 * H),
        flip=ca["lat"], directions="both",
        count_labels=set(DOI_TUONG), margin_frac=bien,
    )


def dem_thu(ca: dict, bien: float) -> tuple[int, int]:
    """Đếm lại từ kết quả phát hiện đã lưu đệm — không cần chạy lại YOLO."""
    d = _phat_hien(ca)
    lc = _bo_dem(ca, d["W"], d["H"], bien)
    for i, (b, ids, nhan) in enumerate(d["khung"]):
        if len(b):
            lc.update(b, ids, nhan, i)
    return lc.in_count, lc.out_count


def dung_video(ca: dict, bien: float, canh_dai: int = 1920, crf: int = 20) -> dict:
    """Phát lại video, vẽ hộp — vạch — bảng đếm, ghi ra tệp MP4.

    Giới hạn cạnh dài ở 1920 và chỉ thu nhỏ chứ không phóng to, nên video 1080p giữ
    nguyên còn video 4K hạ về Full HD.

    Bản trước thu nhỏ về 960 điểm ảnh và nén ở CRF 30 — tham số ấy đặt hồi định nhúng
    video vào bảng tính, nơi mỗi tệp phải lọt dưới 7 MB. Yêu cầu đó đã bỏ nhưng tham số
    thì còn lại, khiến video output mờ hẳn so với khung hình trên giao diện: 1920×1080
    ở 8,3 Mbps bị hạ xuống 960×540 ở 540 kbps, mất ba phần tư số điểm ảnh.

    Giữ nguyên 4K thì ngược lại: một đoạn 1298 khung hình ra tệp 272 MB, quá nặng cho
    thứ chỉ dùng để xem hộp giới hạn và vạch đếm.
    """
    d = _phat_hien(ca)
    W, H, fps = d["W"], d["H"], d["fps"]
    lc = _bo_dem(ca, W, H, bien)
    st = DrawStyle(H)
    x1, y1, x2, y2 = ca["vach"]
    p1 = (int(x1 * W), int(y1 * H))
    p2 = (int(x2 * W), int(y2 * H))

    DEM.mkdir(exist_ok=True)
    tam = DEM / f"_tam_{ca['khoa']}.mp4"
    dich = DEM / f"output_{ca['khoa']}.mp4"
    cap = cv2.VideoCapture(str(GOC / "videos" / ca["tep"]))
    ghi = cv2.VideoWriter(str(tam), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))

    for i, (b, ids, nhan) in enumerate(d["khung"]):
        ok, f = cap.read()
        if not ok:
            break
        if len(b):
            lc.update(b, ids, nhan, i)
            hien_nhan = len(ids) <= 25
            for k, tid in enumerate(ids):
                bx = [int(v) for v in b[k]]
                mau = CLASS_COLORS.get(nhan[k], (0, 200, 255))
                cv2.rectangle(f, (bx[0], bx[1]), (bx[2], bx[3]), mau, st.box)
                if hien_nhan:
                    cv2.putText(f, f"#{tid}", (bx[0] + 4, bx[1] - 6),
                                cv2.FONT_HERSHEY_SIMPLEX, st.font, mau, st.font_th)
        _ve_vach(f, p1, p2, ca["lat"], st)
        _ve_bang(f, ca, lc, st)
        ghi.write(f)

    cap.release()
    ghi.release()

    # OpenCV chỉ ghi được mp4v, mà trình duyệt cần H.264 mới phát trực tiếp được.
    # `force_original_aspect_ratio=decrease` chỉ điều chỉnh tỉ lệ khung, KHÔNG ngăn
    # phóng to: nguồn 384x288 vẫn bị kéo lên 1920x1440, biến một video 632 kbps thành
    # tệp 58 MB mà không thêm chút chi tiết nào. Vì vậy phải tự kiểm tra và bỏ hẳn bước
    # thu phóng khi nguồn đã nhỏ hơn ngưỡng.
    lenh = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(tam)]
    if max(W, H) > canh_dai:
        lenh += ["-vf", f"scale=w={canh_dai}:h={canh_dai}:"
                        "force_original_aspect_ratio=decrease:force_divisible_by=2"]
    lenh += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dich)]
    subprocess.run(lenh, check=True)
    tam.unlink()
    return dict(tep=dich, vao=lc.in_count, ra=lc.out_count,
                khung=len(d["khung"]), tong=d["tong"], W=W, H=H, fps=fps)


def _ve_vach(f, p1, p2, lat, st) -> None:
    cv2.line(f, p1, p2, (0, 255, 255), st.line)
    mx, my = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    chuan = (vx * vx + vy * vy) ** 0.5 or 1
    dai = round(60 * st.s)
    dau = -1 if lat else 1
    nx, ny = int(-vy / chuan * dai * dau), int(vx / chuan * dai * dau)
    cv2.arrowedLine(f, (mx, my), (mx + nx, my + ny), (0, 200, 0), st.font_th + 1, tipLength=.35)
    cv2.putText(f, "VAO", (mx + nx - 18, my + ny), cv2.FONT_HERSHEY_SIMPLEX,
                st.font, (0, 200, 0), st.font_th + 1)
    cv2.arrowedLine(f, (mx, my), (mx - nx, my - ny), (0, 0, 220), st.font_th + 1, tipLength=.35)
    cv2.putText(f, "RA", (mx - nx - 12, my - ny), cv2.FONT_HERSHEY_SIMPLEX,
                st.font, (0, 0, 220), st.font_th + 1)


def _ve_bang(f, ca, lc, st) -> None:
    dong = [ca["ten"], f"VAO: {lc.in_count}   RA: {lc.out_count}"]
    if ca.get("chuan"):
        dong.append(f"nhan chuan: {ca['chuan'][0]} vao / {ca['chuan'][1]} ra")
    rong = round(430 * st.s)
    cao = round(14 * st.s) + len(dong) * st.hud_dy
    phu = f.copy()
    cv2.rectangle(phu, (8, 8), (rong, cao), (0, 0, 0), -1)
    cv2.addWeighted(phu, .45, f, .55, 0, f)
    for i, t in enumerate(dong):
        mau = (200, 200, 200) if i == 2 else ((120, 255, 120) if i else (240, 240, 240))
        cv2.putText(f, t, (round(14 * st.s), round(32 * st.s) + i * st.hud_dy),
                    cv2.FONT_HERSHEY_SIMPLEX, st.hud_font, mau, st.font_th + 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    # Mặc định lấy thẳng từ cấu hình hệ thống, không chép cứng lại: chép cứng thì sửa
    # tham số trong config mà bộ kiểm thử vẫn chạy giá trị cũ, ra bảng kết quả không
    # phản ánh hệ thống thật.
    ap.add_argument("--bien", type=float, default=config.COUNTER_MARGIN_FRAC,
                    help="margin_frac — bề rộng vùng đệm theo chiều cao đối tượng")
    ap.add_argument("--quet", action="store_true", help="chỉ quét hệ số biên")
    ap.add_argument("--bo-du-lieu", action="store_true",
                    help="dựng các chuỗi có nhãn chuẩn thay vì pipeline trong hệ thống")
    args = ap.parse_args()

    cac_ca = nap_ca_bo_du_lieu() if args.bo_du_lieu else nap_cac_ca()

    if args.quet:
        moc = (0.20, 0.15, 0.12, 0.10, 0.08, 0.06, 0.04, 0.02)
        print(f"{'Ca kiểm thử':40s}" + "".join(f"{m:>8}" for m in moc))
        for ca in cac_ca:
            hang = "".join(f"{'%d/%d' % dem_thu(ca, m):>8s}" for m in moc)
            print(f"{ca['ten'][:40]:40s}{hang}")
        return

    ket_qua = []
    for ca in cac_ca:
        r = dung_video(ca, args.bien)
        ket_qua.append({**ca, **r, "tep": str(r["tep"].relative_to(GOC))})
        v = ca["vach"]
        print(f"  {ca['ten'][:40]:42s} vạch ({v[0]:.3f},{v[1]:.3f})→({v[2]:.3f},{v[3]:.3f}) "
              f"lật={str(ca['lat']):5s} vào={r['vao']:3d} ra={r['ra']:3d}  → {r['tep'].name}")
    (DEM / "ket_qua.json").write_text(
        json.dumps(ket_qua, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
