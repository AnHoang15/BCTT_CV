"""Chụp màn hình giao diện ở độ phân giải cao, dùng làm hình minh hoạ cho báo cáo.

Ảnh chụp bằng công cụ có sẵn của trình duyệt thường bị thu nhỏ về khoảng 800 điểm ảnh
ngang — in ra báo cáo thì chữ nhòe. Chương trình này điều khiển Chrome ở chế độ không
giao diện qua giao thức DevTools, đặt hệ số phóng đại 2 lần rồi chụp, cho ảnh sắc nét
gấp đôi.

Cần điều khiển thay vì chỉ mở địa chỉ vì giao diện chuyển trang bằng trạng thái React
chứ không đổi địa chỉ — muốn chụp trang Xem lại thì phải bấm đúng nút.

    python scripts/chup_man_hinh.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websockets

GOC = Path(__file__).resolve().parent.parent
DICH = GOC / "report" / "figures"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CONG = 9333
DIA_CHI = "http://localhost:3000"

# (tệp, chuỗi nút cần bấm theo thứ tự, chờ sau bước cuối, chiều cao khung nhìn)
#
# Phải bấm chứ không mở thẳng địa chỉ vì giao diện chuyển trang bằng trạng thái React,
# địa chỉ không đổi. Mỗi kịch bản bắt đầu lại từ trang Giám sát.
KICH_BAN = [
    ("ui_live.png",          [],                                        3.0, 1000),
    ("ui_alert.png",         ["Lưới 1×1"],                              4.0,  950),
    ("ui_pipeline_list.png", ["Cấu hình"],                              2.5, 1150),
    ("ui_pipeline.png",      ["Cấu hình", "Tạo pipeline mới",
                              "MOT17-04", "Tiếp tục", "Tiếp tục"],      3.0, 1150),
    ("ui_playback.png",      ["Xem lại"],                               4.0, 1150),
]


async def _goi(ws, ph: str, **tham_so):
    _goi.stt = getattr(_goi, "stt", 0) + 1
    await ws.send(json.dumps({"id": _goi.stt, "method": ph, "params": tham_so}))
    while True:
        tl = json.loads(await ws.recv())
        if tl.get("id") == _goi.stt:
            return tl.get("result", {})


async def _bam(ws, nhan: str) -> bool:
    """Bấm nút theo chữ hiển thị, tooltip hoặc nhãn trợ năng.

    Phải xét cả ba vì nhiều nút trên giao diện chỉ có biểu tượng, chữ nằm trong
    thuộc tính `title` chứ không phải nội dung thẻ.
    """
    js = (
        "(() => { const b = [...document.querySelectorAll('button')].find(x =>"
        f" x.textContent.includes({nhan!r})"
        f" || (x.title || '').includes({nhan!r})"
        f" || (x.getAttribute('aria-label') || '').includes({nhan!r}));"
        " if (!b) return false; b.click(); return true; })()"
    )
    r = await _goi(ws, "Runtime.evaluate", expression=js, returnByValue=True)
    return bool(r.get("result", {}).get("value"))


async def _ve_trang_dau(ws):
    """Quay lại trang Giám sát để mỗi kịch bản bắt đầu từ cùng một chỗ."""
    await _goi(ws, "Page.navigate", url=DIA_CHI)
    await asyncio.sleep(3.0)


async def chup():
    DICH.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={CONG}", "--window-size=1600,1000",
         "--user-data-dir=/tmp/chrome-chup", DIA_CHI],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # Chờ Chrome mở cổng gỡ lỗi. Không có vòng chờ thì lần chạy đầu hay hỏng vì
        # Chrome mất một hai giây mới sẵn sàng.
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CONG}/json", timeout=1) as r:
                    tabs = [t for t in json.load(r) if t["type"] == "page"]
                if tabs:
                    ws_url = tabs[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not ws_url:
            raise SystemExit("Chrome không mở được cổng gỡ lỗi")

        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
            await _goi(ws, "Page.enable")
            await _goi(ws, "Runtime.enable")
            for tep, cac_nut, cho, cao in KICH_BAN:
                # deviceScaleFactor=2 cho ảnh gấp đôi độ phân giải, đúng cách màn hình
                # Retina hoạt động — chữ nét chứ không phải phóng to ảnh mờ.
                await _goi(ws, "Emulation.setDeviceMetricsOverride",
                           width=1600, height=cao, deviceScaleFactor=2, mobile=False)
                await _ve_trang_dau(ws)
                hong = None
                for nut in cac_nut:
                    if not await _bam(ws, nut):
                        hong = nut
                        break
                    await asyncio.sleep(1.5)
                if hong:
                    print(f"  bỏ qua {tep}: không thấy nút {hong!r}")
                    continue
                await asyncio.sleep(cho)
                r = await _goi(ws, "Page.captureScreenshot", format="png")
                (DICH / tep).write_bytes(base64.b64decode(r["data"]))
                print(f"  {tep:22s} {1600 * 2}×{cao * 2}  "
                      f"{(DICH / tep).stat().st_size // 1024} KB")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    asyncio.run(chup())
