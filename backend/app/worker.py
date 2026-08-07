"""Luồng xử lý cho một camera.

Mỗi camera chạy trên một luồng riêng, thực hiện vòng lặp:

    đọc khung hình -> (nếu pipeline bật) phát hiện -> bám vết -> đếm vượt vạch
                   -> vẽ chú thích -> đẩy vào bộ đệm cho HTTP stream
                   -> ghi đoạn video + ghi sự kiện/số đếm vào CSDL

Điểm cần lưu ý: HTTP handler không bao giờ chờ camera. Nó chỉ đọc khung hình JPEG mới
nhất trong bộ đệm. Nhờ vậy một camera treo không làm đứng cả API.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime

import cv2
import numpy as np

from . import config, db, detector as detector_mod, language, schedule as schedule_mod
from .counter import CentroidCrossingCounter
from .detector import Detector
from .recorder import SegmentRecorder
from .smart_filter import SmartFilter
from .zone import PolygonZoneCounter

# Màu vẽ theo lớp đối tượng, hệ BGR của OpenCV.
CLASS_COLORS = {
    "person": (0, 200, 255), "bicycle": (255, 180, 0), "car": (0, 220, 120),
    "motorcycle": (255, 120, 200), "bus": (200, 120, 255), "truck": (120, 200, 255),
}


def _parse_source(raw: str):
    """Chuỗi nguồn thành tham số cho cv2.VideoCapture. Số nguyên = webcam."""
    raw = (raw or "").strip()
    if raw.isdigit():
        return int(raw)
    return raw


class DrawStyle:
    """Kích thước nét vẽ tự co giãn theo độ phân giải khung hình.

    Cần thiết vì nét vẽ cố định 2px nhìn rõ trên 720p nhưng mảnh như sợi chỉ trên 4K —
    đây từng là nguyên nhân của báo lỗi "không thấy vạch đếm".
    """

    def __init__(self, height: int) -> None:
        # Cận dưới 0,45 chứ không phải 1,0. Sàn ở 1,0 nghĩa là khung 288 điểm ảnh nhận
        # cùng cỡ chữ tuyệt đối với khung 1080 — bảng số chiếm gần nửa khung hình và
        # dòng tiêu đề tràn ra ngoài. Nguồn camera IP độ phân giải thấp gặp đúng cảnh này.
        s = max(0.45, height / 1080.0)
        self.s = s
        self.box = max(2, round(2 * s))
        self.line = max(3, round(4 * s))
        self.font = 0.55 * s
        self.font_th = max(1, round(1.5 * s))
        self.hud_font = 0.65 * s
        self.hud_dy = round(28 * s)


class PipelineRuntime:
    """Trạng thái riêng của một pipeline đang chạy trên một camera.

    Một camera chạy được nhiều pipeline cùng lúc, ví dụ vừa đếm người qua cửa chính
    vừa đếm xe trong bãi. Mỗi pipeline phải có bộ bám vết, bộ đếm, bộ lọc Thông minh
    và lịch chạy riêng — dùng chung sẽ lẫn số đếm và lẫn mã định danh vết.

    Phần dùng chung được giữ ở `CameraWorker`: giải mã video, một lần gọi YOLO cho mọi
    pipeline, và việc ghi hình.
    """

    def __init__(self, worker: "CameraWorker", pipeline: dict) -> None:
        self.worker = worker
        self.pipeline = pipeline
        self.id = pipeline["id"]

        self.classes = json.loads(pipeline.get("classes") or '["person"]')
        # Luồng Tiêu chuẩn bám vết **mọi** lớp hệ thống hỗ trợ, không chỉ lớp người
        # dùng chọn đếm. Một lượt suy luận YOLO đã tính sẵn cả tám mươi lớp nên việc
        # lọc bớt chỉ vứt kết quả đi chứ không tiết kiệm gì — đo được chênh 2,5%,
        # nằm trong sai số. Nhờ vậy về sau tra cứu được cả những đối tượng chưa ai
        # nghĩ tới lúc cấu hình, thay vì phải dựng pipeline mới rồi ngồi chờ dữ liệu.
        #
        # Luồng Thông minh thì giữ nguyên phạm vi đã chọn: LA-3B lọc theo mô tả của
        # người dùng, đem cả ô tô xe tải vào hỏi vừa tốn GPU vừa vô nghĩa.
        smart = pipeline.get("mode") == "smart"
        self.bam_vet = self.classes if smart else list(config.COCO_CLASSES)
        self.detector = Detector(
            self.bam_vet,
            conf=pipeline.get("conf") or config.YOLO_CONF,
            fps=worker.fps or 30.0,
            smart=smart,
        )
        self.counter: CentroidCrossingCounter | None = None
        self.zone: PolygonZoneCounter | None = None
        self.smart: SmartFilter | None = None
        self.smart_info: dict | None = None
        self.detections: list[dict] = []
        self.frame: np.ndarray | None = None      # khung đã vẽ của riêng pipeline này

        self.schedule = schedule_mod.parse(pipeline.get("schedule"))
        self.in_schedule = schedule_mod.is_active(self.schedule)

        self._last_count_flush = time.time()
        self._last_in = 0
        self._last_out = 0
        self._reset_key: str | None = None
        self._overflow_since: float = 0.0

    @property
    def conf(self) -> float:
        return self.pipeline.get("conf") or config.YOLO_CONF

    def stop_smart(self) -> None:
        if self.smart is not None:
            self.smart.stop()
            self.smart = None

    def reset(self) -> None:
        if self.counter:
            self.counter.reset()
        if self.zone:
            self.zone.reset()
        self.detector.reset_tracker(self.worker.fps or 30.0)
        if self.smart:
            self.smart.reset()
        self._last_in = 0
        self._last_out = 0


class CameraWorker(threading.Thread):
    """Vòng lặp đọc và xử lý video của một camera."""

    def __init__(self, camera: dict) -> None:
        super().__init__(daemon=True, name=f"cam-{camera['id']}")
        self.camera = camera
        self.camera_id = camera["id"]

        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._jpeg: bytes | None = None
        # `_frame` là bản đã vẽ, `_source_frame` là bản nguyên gốc. Trước đây chỉ có
        # một biến tên `_raw_frame` nhưng chứa bản đã vẽ — cái tên đó gây hiểu nhầm.
        self._frame: np.ndarray | None = None
        self._source_frame: np.ndarray | None = None

        self.status = "starting"          # starting | online | offline | stopped
        self.width = 0
        self.height = 0
        self.fps = 0.0
        self.measured_fps = 0.0
        self.latency_ms = 0.0
        self.frame_idx = 0
        self.last_error: str | None = None

        # Các pipeline đang chạy trên camera này, theo thứ tự được gắn vào. Có thể
        # thêm bớt trong lúc worker đang chạy.
        self._pipeline_lock = threading.RLock()
        self.runtimes: dict[str, PipelineRuntime] = {}

        self.recorder = SegmentRecorder(self.camera_id) if config.RECORD_ENABLED else None

    # ── Điều khiển pipeline ──────────────────────────────────────────────────
    def attach_pipeline(self, pipeline: dict | None) -> None:
        """Gắn đúng một pipeline, gỡ hết những cái đang có.

        Giữ lại cho các lời gọi cũ chỉ cần một pipeline. Muốn chạy nhiều pipeline song
        song thì dùng `add_pipeline`.
        """
        with self._pipeline_lock:
            for pipeline_id in list(self.runtimes):
                self.remove_pipeline(pipeline_id)
            if pipeline is not None:
                self.add_pipeline(pipeline)

    def add_pipeline(self, pipeline: dict) -> None:
        """Thêm một pipeline vào camera, hoặc thay thế nếu đã có cùng mã."""
        with self._pipeline_lock:
            self.remove_pipeline(pipeline["id"])
            runtime = PipelineRuntime(self, pipeline)
            self.runtimes[pipeline["id"]] = runtime
            if runtime.schedule:
                db.log(
                    f"Lịch chạy pipeline '{pipeline['name']}': "
                    f"{schedule_mod.describe(runtime.schedule)}",
                    source=f"camera:{self.camera_id}",
                )
            self._rebuild_counter(runtime)
            self._build_smart(runtime)

    def remove_pipeline(self, pipeline_id: str) -> None:
        with self._pipeline_lock:
            runtime = self.runtimes.pop(pipeline_id, None)
            if runtime is not None:
                runtime.stop_smart()

    @property
    def primary(self) -> PipelineRuntime | None:
        """Pipeline đầu tiên — dùng khi cần trả về đúng một giá trị cho tương thích."""
        with self._pipeline_lock:
            return next(iter(self.runtimes.values()), None)

    def _build_smart(self, runtime: PipelineRuntime) -> None:
        """Dựng bộ lọc Thông minh nếu pipeline yêu cầu và câu lệnh thật sự cần LA-3B."""
        pipeline = runtime.pipeline
        if pipeline.get("mode") != "smart":
            runtime.smart_info = None
            return

        prompt = (pipeline.get("prompt") or "").strip()
        if not prompt:
            runtime.smart_info = None
            return

        info = language.describe(prompt)
        runtime.smart_info = info
        if not info["uses_la"]:
            # Câu lệnh chỉ là "người" — YOLO đã lọc được, không cần gọi LA-3B.
            db.log(
                f"Câu lệnh '{prompt}' không cần LA-3B, chạy như luồng Tiêu chuẩn",
                source=f"camera:{self.camera_id}",
            )
            return

        # Vùng đa giác không có vạch để đệm lượt vượt, truyền một đoạn giả để
        # SmartFilter vẫn dựng được; phần đệm chỉ dùng cho bài toán đếm qua vạch.
        if runtime.counter is not None:
            p1, p2 = runtime.counter.p1, runtime.counter.p2
        elif runtime.zone is not None:
            p1, p2 = (0.0, 0.0), (float(self.width or 1), 0.0)
        else:
            return

        runtime.smart = SmartFilter(
            info["query"], p1, p2, flip=bool(pipeline.get("flip")),
        )
        runtime.smart.on_confirmed = (
            lambda track_id, net, rt=runtime: self._on_smart_confirmed(rt, track_id, net)
        )
        db.log(
            f"Luồng Thông minh: '{prompt}' → truy vấn LA-3B '{info['query']}' "
            f"(chiều: {info['direction']})",
            source=f"camera:{self.camera_id}",
        )

    def _on_smart_confirmed(self, runtime: PipelineRuntime, track_id: int,
                            net: int) -> None:
        """LA-3B xác nhận một vết khớp mô tả: cộng bù các lượt đã đệm."""
        counter = runtime.counter
        if counter is None:
            return

        direction = "in" if net > 0 else "out"
        if not self._direction_wanted(runtime, direction):
            return
        for _ in range(abs(net)):
            if net > 0:
                counter.in_count += 1
            else:
                counter.out_count += 1
        frame = runtime.frame if runtime.frame is not None else self.get_frame()
        if frame is not None:
            self._record_crossing(
                {"track_id": track_id, "direction": direction,
                 "label": "person", "box": [0, 0, 0, 0]},
                frame, runtime.pipeline,
            )

    def _direction_wanted(self, runtime: PipelineRuntime, direction: str) -> bool:
        """Câu lệnh có giới hạn chiều đếm hay không (vd 'người đeo ba lô đi vào')."""
        if not runtime.smart_info:
            return True
        wanted = runtime.smart_info.get("direction", "both")
        return wanted == "both" or wanted == direction

    def _rebuild_counter(self, runtime: PipelineRuntime) -> None:
        """Dựng bộ đếm từ hình vẽ chuẩn hoá của pipeline.

        Bài toán `counting` dùng vạch thẳng, `zone` dùng vùng đa giác. Toạ độ lưu ở dạng
        chuẩn hoá 0..1 nên phải nhân với kích thước khung hình thật tại đây.
        """
        if not self.width:
            return

        pipeline = runtime.pipeline
        runtime.counter = None
        runtime.zone = None

        if pipeline.get("task") == "zone":
            points = json.loads(pipeline.get("zone") or "[]")
            if len(points) < 3:
                # Chưa vẽ đủ đỉnh: lấy tạm vùng giữa khung để pipeline vẫn chạy được.
                points = [{"x": 0.25, "y": 0.25}, {"x": 0.75, "y": 0.25},
                          {"x": 0.75, "y": 0.75}, {"x": 0.25, "y": 0.75}]
            pixels = [(p["x"] * self.width, p["y"] * self.height) for p in points]
            runtime.zone = PolygonZoneCounter(
                pixels,
                debounce=config.COUNTER_DEBOUNCE,
                # Ở luồng Thông minh, vết chỉ hiện ra sau khi LA-3B xác nhận, nên lần
                # đầu nhìn thấy nó trong vùng đã là một lượt vào thật sự.
                count_initial=pipeline.get("mode") == "smart",
                # Vùng ghi nhận mọi lớp, chỉ cộng vào số đếm lớp đã chọn.
                count_labels=set(runtime.classes),
            )
            runtime._last_in = 0
            runtime._last_out = 0
            return

        line = json.loads(pipeline.get("line") or "{}")
        if not line:
            line = {"x1": 0.0, "y1": 0.55, "x2": 1.0, "y2": 0.55}
        p1 = (line["x1"] * self.width, line["y1"] * self.height)
        p2 = (line["x2"] * self.width, line["y2"] * self.height)
        # Chiều đếm lấy từ cấu hình; riêng chế độ Thông minh thì câu lệnh tiếng Việt
        # được ưu tiên, vì "người đeo ba lô đi vào" đã nói rõ chiều rồi.
        directions = pipeline.get("direction") or "both"
        if pipeline.get("mode") == "smart" and pipeline.get("prompt"):
            from_prompt = language.parse_command(pipeline["prompt"])[1]
            if from_prompt != "both":
                directions = from_prompt

        runtime.counter = CentroidCrossingCounter(
            p1, p2,
            history_len=config.COUNTER_HISTORY,
            cooldown_frames=config.COUNTER_COOLDOWN,
            relink_dist=config.COUNTER_RELINK_DIST,
            margin_frac=config.COUNTER_MARGIN_FRAC,
            debounce=config.COUNTER_DEBOUNCE,
            flip=bool(pipeline.get("flip")),
            directions=directions,
            # Vạch ghi nhận mọi lớp, chỉ cộng vào số đếm lớp đã chọn.
            count_labels=set(runtime.classes),
        )
        runtime._last_in = 0
        runtime._last_out = 0

    def reset_counter(self, pipeline_id: str | None = None) -> None:
        """Đặt lại số đếm. Không truyền mã thì đặt lại toàn bộ pipeline của camera."""
        with self._pipeline_lock:
            targets = (
                [self.runtimes[pipeline_id]] if pipeline_id in self.runtimes
                else list(self.runtimes.values()) if pipeline_id is None
                else []
            )
            for runtime in targets:
                runtime.reset()

    # ── Truy cập khung hình ──────────────────────────────────────────────────
    def get_jpeg(self) -> bytes | None:
        with self._frame_lock:
            return self._jpeg

    def get_frame(self) -> np.ndarray | None:
        """Khung hình đã vẽ, dạng mảng chưa nén."""
        with self._frame_lock:
            return None if self._frame is None else self._frame.copy()

    def get_source_frame(self) -> np.ndarray | None:
        """Khung hình nguyên bản, chưa vẽ gì lên."""
        with self._frame_lock:
            return None if self._source_frame is None else self._source_frame.copy()

    def get_pipeline_frame(self, pipeline_id: str | None) -> np.ndarray | None:
        """Khung hình đã vẽ của riêng một pipeline.

        Không truyền mã, hoặc mã không khớp pipeline nào đang chạy, thì trả bản của
        pipeline đầu tiên — vẫn hơn là trả khung đen.
        """
        with self._pipeline_lock:
            runtime = self.runtimes.get(pipeline_id) if pipeline_id else None
            if runtime is None:
                runtime = next(iter(self.runtimes.values()), None)
            frame = runtime.frame if runtime else None
        return None if frame is None else frame.copy()

    def stop(self) -> None:
        self._stop_event.set()

    def _runtime_state(self, runtime: PipelineRuntime) -> dict:
        """Phần trạng thái thuộc về riêng một pipeline."""
        counter, zone = runtime.counter, runtime.zone
        return {
            **(runtime.smart.stats() if runtime.smart else {}),
            "pipeline_id": runtime.id,
            "pipeline_name": runtime.pipeline["name"],
            "mode": runtime.pipeline.get("mode", "standard"),
            "task": runtime.pipeline.get("task"),
            "smart_info": runtime.smart_info,
            "in_schedule": runtime.in_schedule,
            "schedule_text": schedule_mod.describe(runtime.schedule),
            "in_count": (
                counter.in_count if counter
                else zone.total_entered if zone else 0
            ),
            "out_count": counter.out_count if counter else 0,
            "in_zone": zone.current if zone else 0,
            "occupancy": len(runtime.detections),
            "detections": runtime.detections,
        }

    def snapshot_state(self) -> dict:
        """Trạng thái tức thời để trả về qua API.

        `pipelines` liệt kê mọi pipeline đang chạy trên camera. Các trường số đếm ở
        cấp ngoài cùng là của pipeline đầu tiên — giữ lại để phần giao diện chưa
        chuyển sang đọc danh sách vẫn hoạt động.
        """
        with self._pipeline_lock:
            runtimes = list(self.runtimes.values())
            states = [self._runtime_state(r) for r in runtimes]

        camera_state = {
            "camera_id": self.camera_id,
            "status": self.status,
            "width": self.width,
            "height": self.height,
            "fps": round(self.measured_fps, 1),
            "latency_ms": round(self.latency_ms),
            "frame_idx": self.frame_idx,
            "error": self.last_error,
            "pipelines": states,
        }
        first = states[0] if states else {
            "pipeline_id": None, "pipeline_name": None, "mode": None,
            "smart_info": None, "in_schedule": True, "schedule_text": None,
            "in_count": 0, "out_count": 0, "in_zone": 0,
            "occupancy": 0, "detections": [],
        }
        return {**first, **camera_state}

    # ── Vòng lặp chính ───────────────────────────────────────────────────────
    def run(self) -> None:
        source = _parse_source(self.camera["source"])
        failures = 0
        while not self._stop_event.is_set():
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                cap.release()
                self.status = "offline"
                self.last_error = f"Không mở được nguồn: {source}"
                failures += 1

                # Camera đã bị tắt thì thôi hẳn. Trước đây worker cứ thử lại mãi kể cả
                # khi người dùng đã tắt camera: một webcam khai báo sẵn nhưng không cắm
                # vào máy sẽ sinh lỗi OpenCV mỗi ba giây cho tới khi tắt backend.
                row = db.query_one(
                    "SELECT enabled FROM cameras WHERE id=?", (self.camera_id,)
                )
                if row is None or not row["enabled"]:
                    self.status = "stopped"
                    break

                # Chỉ ghi nhật ký lần hỏng đầu tiên. Ghi mọi lần thì bảng nhật ký đầy
                # rác và những sự kiện đáng chú ý khác bị lấp mất.
                if failures == 1:
                    db.log(self.last_error, level="error",
                           source=f"camera:{self.camera_id}")

                # Giãn dần: 3s, 6s, 12s… tới trần. Nguồn hỏng hẳn thì thử lại dày đặc
                # cũng vô ích, chỉ tốn CPU và làm bẩn nhật ký.
                delay = min(
                    config.RECONNECT_DELAY_S * 2 ** min(failures - 1, 5),
                    config.RECONNECT_MAX_DELAY_S,
                )
                if self._stop_event.wait(delay):
                    break
                continue

            failures = 0

            self._on_connected(cap)
            try:
                self._capture_loop(cap, source)
            finally:
                cap.release()

            if not self._stop_event.is_set():
                self.status = "offline"
                self._stop_event.wait(config.RECONNECT_DELAY_S)

        if self.recorder:
            self.recorder.stop()
        with self._pipeline_lock:
            for runtime in self.runtimes.values():
                runtime.stop_smart()
        self.status = "stopped"

    def _on_connected(self, cap) -> None:
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.status = "online"
        self.last_error = None
        # Toạ độ vạch và vùng lưu ở dạng chuẩn hoá, phải biết kích thước khung hình
        # thật mới dựng được bộ đếm. Pipeline gắn vào trước lúc kết nối thì tới đây
        # mới có đủ thông tin.
        with self._pipeline_lock:
            for runtime in self.runtimes.values():
                if runtime.counter is None and runtime.zone is None:
                    self._rebuild_counter(runtime)
                    self._build_smart(runtime)
        db.log(
            f"Kết nối camera {self.camera['name']} — {self.width}x{self.height} "
            f"@{self.fps:.0f}fps",
            source=f"camera:{self.camera_id}",
        )

    def _capture_loop(self, cap, source) -> None:
        is_file = isinstance(source, str) and not source.startswith(
            ("rtsp://", "http://", "https://")
        )
        times: list[float] = []
        last_loop_start: float | None = None

        while not self._stop_event.is_set():
            loop_start = time.time()
            ok, frame = cap.read()
            if not ok:
                if is_file:
                    # Video từ tệp: phát lặp lại để demo chạy liên tục.
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.reset_counter()
                    continue
                self.last_error = "Mất tín hiệu"
                db.log("Mất tín hiệu camera", level="warning",
                       source=f"camera:{self.camera_id}")
                return

            annotated = self._process(frame)

            if self.recorder:
                self.recorder.write(annotated)

            self._publish(annotated, source=frame)
            self.frame_idx += 1
            self._apply_auto_reset()
            self._check_overflow(annotated)

            elapsed = time.time() - loop_start
            # `latency_ms` là thời gian xử lý một khung hình — cho biết máy có kịp
            # không. `measured_fps` phải là nhịp chạy THẬT, tức khoảng cách giữa hai
            # vòng lặp liên tiếp (đã tính cả thời gian nghỉ). Nếu chỉ lấy nghịch đảo
            # thời gian xử lý thì màn hình sẽ báo 26 FPS trong khi người dùng đặt 10.
            self.latency_ms = elapsed * 1000
            if last_loop_start is not None:
                times.append(loop_start - last_loop_start)
                if len(times) > 30:
                    times.pop(0)
                self.measured_fps = 1.0 / (sum(times) / len(times)) if times else 0.0
            last_loop_start = loop_start

            self._flush_counts()

            # Giữ nhịp mục tiêu để không chiếm hết CPU khi nguồn là tệp video. Pipeline
            # có thể đặt nhịp riêng, đọc lại mỗi vòng để đổi cấu hình là ăn ngay. Nhiều
            # pipeline trên một camera thì lấy nhịp cao nhất, vì camera chỉ có một vòng
            # lặp: chạy chậm hơn thì pipeline đòi nhanh sẽ bị hụt khung hình.
            with self._pipeline_lock:
                rates = [
                    r.pipeline.get("target_fps") or config.TARGET_FPS
                    for r in self.runtimes.values()
                ]
            target = max(rates) if rates else config.TARGET_FPS
            sleep_for = 1.0 / max(1.0, float(target)) - elapsed
            if sleep_for > 0:
                if self._stop_event.wait(sleep_for):
                    return

    # ── Xử lý một khung hình ─────────────────────────────────────────────────
    def _process(self, frame: np.ndarray) -> np.ndarray:
        """Chạy mọi pipeline của camera trên một khung hình.

        Trả về khung hình dùng cho luồng xem chung và cho việc ghi hình; mỗi pipeline
        còn giữ bản vẽ riêng của nó trong `runtime.frame`.
        """
        with self._pipeline_lock:
            runtimes = list(self.runtimes.values())

        if not runtimes:
            return frame

        # Pipeline nào tới giờ chạy. Ngoài khung giờ thì bỏ qua phần nhận diện của
        # riêng pipeline đó; luồng video và việc ghi hình vẫn tiếp tục.
        active_runtimes = []
        for runtime in runtimes:
            active = schedule_mod.is_active(runtime.schedule)
            if active != runtime.in_schedule:
                runtime.in_schedule = active
                db.log(
                    f"Pipeline '{runtime.pipeline['name']}' "
                    f"{'vào' if active else 'ra khỏi'} khung giờ chạy",
                    source=f"camera:{self.camera_id}",
                )
            if active:
                active_runtimes.append(runtime)
            else:
                runtime.detections = []
                runtime.frame = self._annotate_idle(frame)

        if not active_runtimes:
            return runtimes[0].frame if runtimes[0].frame is not None else frame

        # Một lần gọi YOLO cho tất cả: hợp các lớp cần tìm, lấy ngưỡng tin cậy thấp
        # nhất rồi để từng pipeline tự lọc lại. Gọi riêng cho mỗi pipeline sẽ nhân
        # đôi nhân ba chi phí GPU, mà GPU đang là nút thắt của cả hệ thống.
        wanted: list[int] = []
        for runtime in active_runtimes:
            for class_id in runtime.detector.class_ids:
                if class_id not in wanted:
                    wanted.append(class_id)
        min_conf = min(runtime.conf for runtime in active_runtimes)
        shared = detector_mod.detect(frame, wanted, min_conf)

        for runtime in active_runtimes:
            self._process_one(runtime, frame, shared)

        return active_runtimes[0].frame

    def _process_one(self, runtime: PipelineRuntime, frame: np.ndarray, shared) -> None:
        """Bám vết, đếm và vẽ cho riêng một pipeline."""
        pipeline = runtime.pipeline
        boxes, track_ids, labels, confs = runtime.detector.track(shared)

        # Luồng Thông minh: chỉ giữ các vết LA-3B đã xác nhận khớp mô tả.
        if runtime.smart is not None and len(track_ids):
            mask = runtime.smart.apply(frame, boxes, track_ids)
            boxes = boxes[mask]
            track_ids = [t for t, keep in zip(track_ids, mask) if keep]
            labels = [l for l, keep in zip(labels, mask) if keep]
            confs = [c for c, keep in zip(confs, mask) if keep]

        # `detections` chỉ giữ lớp người dùng chọn đếm, vì nó nuôi con số "Trong khung"
        # trên màn hình và ngưỡng cảnh báo vượt số lượng. Camera bám vết cả sáu lớp để
        # về sau tra cứu được, nhưng nếu để ô tô lọt vào đây thì cảnh báo "quá đông
        # người" sẽ nổ vì một chiếc xe chạy ngang.
        chon = set(runtime.classes)
        runtime.detections = [
            {
                "track_id": track_ids[i],
                "label": labels[i],
                "confidence": round(float(confs[i]), 3),
                "box": [round(float(v)) for v in boxes[i]],
            }
            for i in range(len(track_ids))
            if labels[i] in chon
        ]

        crossings: list[dict] = []
        if runtime.counter is not None and pipeline["task"] == "counting":
            crossings = runtime.counter.update(boxes, track_ids, labels, self.frame_idx)
            if self.frame_idx % 300 == 0:
                runtime.counter.prune(self.frame_idx)
        elif runtime.zone is not None and pipeline["task"] == "zone":
            crossings = runtime.zone.update(boxes, track_ids, labels, self.frame_idx)
            if self.frame_idx % 300 == 0:
                runtime.zone.prune(self.frame_idx)

        runtime.frame = self._annotate(runtime, frame, boxes, track_ids, labels)

        for event in crossings:
            self._record_crossing(event, runtime.frame, pipeline)

    def _save_snapshot(self, frame: np.ndarray, suffix: str) -> str | None:
        """Lưu ảnh chụp kèm sự kiện. Trả về tên tệp, hoặc None nếu ghi thất bại.

        Thu nhỏ về chiều rộng `SNAPSHOT_MAX_WIDTH` trước khi lưu: khung hình gốc từ
        camera 4K (~2160x3840) tới ~550KB/ảnh, thu về 320px chỉ còn vài chục KB —
        giảm chục lần dung lượng đĩa mà vẫn đủ chi tiết để xem lại sự kiện.
        """
        ts = datetime.now()
        name = f"{self.camera_id}_{ts.strftime('%Y%m%d_%H%M%S')}_{suffix}.jpg"
        try:
            scale = min(1.0, config.SNAPSHOT_MAX_WIDTH / max(1, frame.shape[1]))
            if scale < 1.0:
                size = (int(frame.shape[1] * scale), int(frame.shape[0] * scale))
                frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(config.SNAPSHOT_DIR / name), frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 80])
            return name
        except Exception as exc:  # ổ đĩa đầy, quyền ghi...
            db.log(f"Không lưu được ảnh chụp: {exc}", level="error",
                   source=f"camera:{self.camera_id}")
            return None

    def _record_event(self, frame: np.ndarray, pipeline: dict, event_type: str,
                      message: str, **fields) -> None:
        """Ghi một sự kiện bất kỳ kèm ảnh chụp."""
        db.insert_event(
            camera_id=self.camera_id,
            pipeline_id=pipeline["id"],
            type=event_type,
            snapshot=self._save_snapshot(frame, event_type),
            message=message,
            **fields,
        )

    def _record_crossing(self, event: dict, frame: np.ndarray, pipeline: dict) -> None:
        """Lưu ảnh chụp và ghi sự kiện vượt vạch vào CSDL."""
        name = self._save_snapshot(frame, str(event["track_id"]))

        label_vi = config.CLASS_LABELS_VI.get(event["label"], event["label"])
        direction_vi = "đi vào" if event["direction"] == "in" else "đi ra"
        db.insert_event(
            camera_id=self.camera_id,
            pipeline_id=pipeline["id"],
            type="crossing",
            direction=event["direction"],
            label=event["label"],
            track_id=event["track_id"],
            snapshot=name,
            message=f"{label_vi} {direction_vi} (ID #{event['track_id']})",
        )

    def _apply_auto_reset(self) -> None:
        """Tự động đưa số đếm về 0 theo chu kỳ giờ hoặc ngày, riêng từng pipeline."""
        with self._pipeline_lock:
            runtimes = list(self.runtimes.values())

        now = datetime.now()
        for runtime in runtimes:
            mode = runtime.pipeline.get("auto_reset") or "never"
            if mode == "never":
                runtime._reset_key = None
                continue

            key = now.strftime("%Y%m%d%H") if mode == "hourly" else now.strftime("%Y%m%d")
            if runtime._reset_key is None:
                # Lần đầu chỉ ghi nhận mốc, không đặt lại — tránh xoá số đếm ngay khi bật.
                runtime._reset_key = key
                continue
            if key != runtime._reset_key:
                runtime._reset_key = key
                runtime.reset()
                db.log(
                    f"Tự động đặt lại số đếm pipeline '{runtime.pipeline['name']}' "
                    f"theo chu kỳ {'giờ' if mode == 'hourly' else 'ngày'}",
                    source=f"camera:{self.camera_id}",
                )

    def _check_overflow(self, frame) -> None:
        """Cảnh báo khi số đối tượng vượt ngưỡng người dùng đặt.

        Có khoảng nghỉ giữa hai lần cảnh báo, nếu không thì đám đông đứng yên sẽ sinh
        ra một cảnh báo mỗi khung hình.
        """
        with self._pipeline_lock:
            runtimes = list(self.runtimes.values())

        for runtime in runtimes:
            limit = runtime.pipeline.get("max_count")
            if not limit:
                continue

            zone = runtime.zone
            current = zone.current if zone is not None else len(runtime.detections)
            if current <= limit:
                runtime._overflow_since = 0.0
                continue
            if time.time() - runtime._overflow_since < config.OVERFLOW_COOLDOWN_SECONDS:
                continue
            runtime._overflow_since = time.time()

            where = "trong vùng" if zone is not None else "trong khung hình"
            self._record_event(
                runtime.frame if runtime.frame is not None else frame,
                runtime.pipeline,
                event_type="overflow",
                message=f"Vượt ngưỡng: {current} đối tượng {where} (giới hạn {limit})",
            )

    def _flush_counts(self) -> None:
        """Định kỳ ghi mốc số đếm của từng pipeline để vẽ biểu đồ theo thời gian."""
        with self._pipeline_lock:
            runtimes = list(self.runtimes.values())

        now = time.time()
        for runtime in runtimes:
            counter, zone = runtime.counter, runtime.zone
            if counter is None and zone is None:
                continue
            if now - runtime._last_count_flush < config.COUNT_SNAPSHOT_SECONDS:
                continue

            if counter is not None:
                total_in, total_out = counter.in_count, counter.out_count
                occupancy = len(runtime.detections)
            else:
                total_in, total_out = zone.total_entered, 0
                occupancy = zone.current

            db.insert_count(
                self.camera_id, runtime.id, total_in, total_out,
                total_in - runtime._last_in, total_out - runtime._last_out, occupancy,
            )
            runtime._last_in = total_in
            runtime._last_out = total_out
            runtime._last_count_flush = now

    # ── Vẽ chú thích ─────────────────────────────────────────────────────────
    def _annotate(self, runtime, frame, boxes, track_ids, labels):
        counter, pipeline = runtime.counter, runtime.pipeline
        out = frame.copy()
        st = DrawStyle(out.shape[0])

        show_labels = len(track_ids) <= config.LABEL_HIDE_ABOVE
        for i, tid in enumerate(track_ids):
            x1, y1, x2, y2 = [int(v) for v in boxes[i]]
            color = CLASS_COLORS.get(labels[i], (0, 200, 255))
            cv2.rectangle(out, (x1, y1), (x2, y2), color, st.box)
            if show_labels:
                text = f"#{tid}"
                (tw, th), _ = cv2.getTextSize(
                    text, cv2.FONT_HERSHEY_SIMPLEX, st.font, st.font_th
                )
                cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 8, y1), color, -1)
                cv2.putText(out, text, (x1 + 4, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, st.font, (20, 20, 20), st.font_th)

        if counter is not None and pipeline["task"] == "counting":
            self._draw_line(out, counter, st)
        elif runtime.zone is not None and pipeline["task"] == "zone":
            self._draw_zone(out, runtime.zone, st)

        self._draw_hud(out, runtime, st)
        return out

    def _annotate_idle(self, frame):
        """Khung hình lúc ngoài giờ chạy: chỉ ghi rõ AI đang nghỉ theo lịch."""
        out = frame.copy()
        st = DrawStyle(out.shape[0])
        lines = [
            f"{self.camera['name']}  |  {self.measured_fps:.1f} FPS",
            "Ngoai khung gio chay - AI tam nghi",
        ]
        width = round(420 * st.s)
        height = round(14 * st.s) + len(lines) * st.hud_dy
        overlay = out.copy()
        cv2.rectangle(overlay, (8, 8), (width, height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, out, 0.55, 0, out)
        for i, text in enumerate(lines):
            color = (140, 190, 255) if i else (240, 240, 240)
            cv2.putText(out, text, (round(14 * st.s), round(32 * st.s) + i * st.hud_dy),
                        cv2.FONT_HERSHEY_SIMPLEX, st.hud_font, color, st.font_th + 1)
        return out

    def _draw_zone(self, frame, zone, st) -> None:
        """Vẽ vùng đa giác: viền vàng và lớp phủ mờ bên trong."""
        pts = zone.polygon.reshape(-1, 2).astype(np.int32)
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], (0, 200, 200))
        cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
        cv2.polylines(frame, [pts], True, (0, 255, 255), st.line)
        for point in pts:
            cv2.circle(frame, tuple(point), max(3, st.line + 1), (0, 255, 255), -1)

    def _draw_line(self, frame, counter, st) -> None:
        p1 = (int(counter.p1[0]), int(counter.p1[1]))
        p2 = (int(counter.p2[0]), int(counter.p2[1]))
        cv2.line(frame, p1, p2, (0, 255, 255), st.line)

        # Mũi tên chỉ rõ phía nào tính là Vào, phía nào là Ra.
        mx, my = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
        vx, vy = p2[0] - p1[0], p2[1] - p1[1]
        norm = (vx * vx + vy * vy) ** 0.5 or 1
        length = round(60 * st.s)
        sign = -1 if counter.flip else 1
        nx = int(-vy / norm * length * sign)
        ny = int(vx / norm * length * sign)

        cv2.arrowedLine(frame, (mx, my), (mx + nx, my + ny), (0, 200, 0),
                        st.font_th + 1, tipLength=0.35)
        cv2.putText(frame, "VAO", (mx + nx - 18, my + ny),
                    cv2.FONT_HERSHEY_SIMPLEX, st.font, (0, 200, 0), st.font_th + 1)
        cv2.arrowedLine(frame, (mx, my), (mx - nx, my - ny), (0, 0, 220),
                        st.font_th + 1, tipLength=0.35)
        cv2.putText(frame, "RA", (mx - nx - 12, my - ny),
                    cv2.FONT_HERSHEY_SIMPLEX, st.font, (0, 0, 220), st.font_th + 1)

    def _draw_hud(self, frame, runtime, st) -> None:
        counter, zone, pipeline = runtime.counter, runtime.zone, runtime.pipeline
        lines = [f"{self.camera['name']}  |  {self.measured_fps:.1f} FPS"]
        lines.append(pipeline["name"])
        if runtime.smart_info:
            # OpenCV không vẽ được chữ có dấu, dùng truy vấn tiếng Anh đã dịch.
            lines.append(f"Loc: {runtime.smart_info['query'][:34]}")
        if counter is not None and pipeline["task"] == "counting":
            lines.append(f"VAO: {counter.in_count}   RA: {counter.out_count}")
        elif zone is not None and pipeline["task"] == "zone":
            lines.append(
                f"TRONG VUNG: {zone.current}   DA VAO: {zone.total_entered}"
            )
        lines.append(f"Trong khung: {len(runtime.detections)}")
        if runtime.smart is not None:
            stats = runtime.smart.stats()
            lines.append(
                f"Khop: {stats['la_matched']}  Loai: {stats['la_rejected']}"
                f"  Cho: {stats['la_pending']}"
            )

        width = round(360 * st.s)
        height = round(14 * st.s) + len(lines) * st.hud_dy
        overlay = frame.copy()
        cv2.rectangle(overlay, (8, 8), (width, height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        for i, text in enumerate(lines):
            color = (120, 255, 160) if text.startswith("VAO") else (240, 240, 240)
            cv2.putText(frame, text, (round(14 * st.s), round(32 * st.s) + i * st.hud_dy),
                        cv2.FONT_HERSHEY_SIMPLEX, st.hud_font, color, st.font_th + 1)

    def _publish(self, frame: np.ndarray, source: np.ndarray | None = None) -> None:
        """Nén JPEG một lần rồi chia sẻ cho mọi client đang xem.

        Giữ lại hai bản. `frame` là bản đã vẽ hộp giới hạn, vạch đếm và số đếm — dùng
        cho luồng xem trực tiếp và cho ảnh đính kèm mỗi cảnh báo. `source` là khung
        hình nguyên bản, dùng khi cấu hình pipeline mới trên camera đã có pipeline
        khác đang chạy: vẽ vạch mới lên nền đầy hộp giới hạn của pipeline cũ thì rối
        mắt và dễ đặt nhầm chỗ.
        """
        scale = min(1.0, config.STREAM_MAX_WIDTH / max(1, frame.shape[1]))
        if scale < 1.0:
            size = (int(frame.shape[1] * scale), int(frame.shape[0] * scale))
            frame = cv2.resize(frame, size)
            # Thu nhỏ cùng cỡ để toạ độ chuẩn hoá của vạch và vùng khớp giữa hai bản.
            if source is not None:
                source = cv2.resize(source, size)
        ok, buf = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, config.STREAM_JPEG_QUALITY]
        )
        if not ok:
            return
        with self._frame_lock:
            self._jpeg = buf.tobytes()
            self._frame = frame
            self._source_frame = frame if source is None else source
