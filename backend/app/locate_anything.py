"""Nạp và gọi LocateAnything-3B (LA-3B).

LA-3B là mô hình thị giác–ngôn ngữ định vị vật thể theo mô tả tự do. Trong hệ thống này
nó đóng vai trò bộ lọc: YOLO đề xuất hộp, LA-3B quyết định hộp nào khớp với mô tả của
người dùng.

Repo gốc của LA-3B viết cho một phiên bản thư viện cũ hơn nên phải vá vài chỗ trước khi
nạp được, xem `_apply_patches()`. Toàn bộ việc nạp là lazy: chỉ chạy khi có pipeline
Thông minh được kích hoạt, vì mô hình chiếm khoảng 8 GB bộ nhớ.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import types
from pathlib import Path

import cv2
import numpy as np

from . import config

_READY = False
_LOAD_LOCK = threading.RLock()
# LA-3B không an toàn khi nhiều luồng cùng gọi; nối tiếp các lần suy luận.
_INFER_LOCK = threading.Lock()
_generate_batch_hybrid = None
_LOAD_ERROR: str | None = None


def model_dir() -> Path:
    return Path(config.LA3B_MODEL_DIR)


def is_available() -> bool:
    """Có thư mục mô hình trên đĩa hay không. Không nạp mô hình."""
    directory = model_dir()
    return (directory / "config.json").exists() and (directory / "batch_utils").is_dir()


def status() -> dict:
    return {
        "available": is_available(),
        "loaded": _READY,
        "path": str(model_dir()),
        "error": _LOAD_ERROR,
    }


def _apply_patches(directory: Path) -> None:
    """Vá các điểm không tương thích giữa repo LA-3B và thư viện hiện tại."""
    # 1. config.json thiếu vài khoá mà Qwen2 đời mới bắt buộc phải có.
    config_path = directory / "config.json"
    cfg = json.loads(config_path.read_text())
    changed = False
    for key, value in (
        ("rope_theta", 1000000.0),
        ("use_sliding_window", False),
        ("sliding_window", None),
        ("max_window_layers", 28),
    ):
        if key not in cfg:
            cfg[key] = value
            changed = True
    if "vision_config" in cfg:
        vision = cfg["vision_config"]
        if vision.get("_name_or_path") != str(directory):
            vision["_name_or_path"] = str(directory)
            vision["auto_map"] = {
                "AutoConfig": "modeling_vit.MoonViTConfig",
                "AutoModel": "modeling_vit.MoonVitPretrainedModel",
            }
            changed = True
    if changed:
        config_path.write_text(json.dumps(cfg, indent=2))

    # 2. Checkpoint khai báo kiến trúc qwen3 nhưng thực chất là Qwen2. Bản transformers
    #    cũ chưa có module qwen3 nên phải trỏ tạm sang qwen2.
    try:
        import transformers.models.qwen3.configuration_qwen3  # noqa: F401
    except ImportError:
        from transformers.models.qwen2.configuration_qwen2 import Qwen2Config
        from transformers.models.qwen2.modeling_qwen2 import Qwen2ForCausalLM

        package = types.ModuleType("transformers.models.qwen3")
        conf_mod = types.ModuleType("transformers.models.qwen3.configuration_qwen3")
        model_mod = types.ModuleType("transformers.models.qwen3.modeling_qwen3")
        conf_mod.Qwen3Config = Qwen2Config
        model_mod.Qwen3ForCausalLM = Qwen2ForCausalLM
        sys.modules["transformers.models.qwen3"] = package
        sys.modules["transformers.models.qwen3.configuration_qwen3"] = conf_mod
        sys.modules["transformers.models.qwen3.modeling_qwen3"] = model_mod

    # 3. `decord` và `lmdb` chỉ dùng cho nhánh xử lý video của repo gốc. Ta chỉ suy luận
    #    trên ảnh nên tạo module rỗng cho qua bước kiểm tra import.
    for name in ("decord", "lmdb"):
        if name not in sys.modules:
            try:
                __import__(name)
            except ImportError:
                sys.modules[name] = types.ModuleType(name)


def load() -> bool:
    """Nạp LA-3B. Trả về True nếu sẵn sàng. An toàn khi gọi nhiều lần."""
    global _READY, _generate_batch_hybrid, _LOAD_ERROR

    with _LOAD_LOCK:
        if _READY:
            return True
        directory = model_dir()
        if not is_available():
            _LOAD_ERROR = (
                f"Không tìm thấy mô hình tại {directory}. "
                "Đặt biến môi trường LA3B_MODEL_DIR trỏ tới thư mục LocateAnything-3B."
            )
            return False

        try:
            import os
            import torch

            os.environ["LA_FLASH_MODEL"] = str(directory)
            # Mac không có flash-attn; sdpa là cài đặt attention có sẵn trong PyTorch.
            os.environ["LA_FLASH_ATTN"] = "sdpa"
            os.environ["LA_FLASH_VISION_ATTN"] = "sdpa"
            os.environ["MTP_COMPILE"] = "0"

            _apply_patches(directory)

            if str(directory) not in sys.path:
                sys.path.insert(0, str(directory))

            import batch_utils.engine_hybrid as engine_hybrid
            import batch_utils.hybrid_runtime as hybrid_runtime

            device = config.device()
            hybrid_runtime.DEV = device
            engine_hybrid.DEV = device

            from batch_utils import generate_batch_hybrid, load as la_load

            # Nạp cũng là thao tác chạm GPU: đẩy 7,3 GB trọng số lên Metal trong khi
            # các luồng camera đang chạy YOLO là đúng tình huống làm hỏng bộ nhớ.
            with config.inference_guard():
                la_load()
            _generate_batch_hybrid = generate_batch_hybrid
            _READY = True
            _LOAD_ERROR = None

            used = ""
            if device == "mps":
                used = f" | bộ nhớ {torch.mps.driver_allocated_memory() / 1e9:.1f} GB"
            elif device == "cuda":
                used = f" | bộ nhớ {torch.cuda.memory_allocated() / 1e9:.1f} GB"
            print(f"[LA-3B] Đã nạp trên {device}{used}")
            return True

        except Exception as exc:  # thiếu thư viện, hết bộ nhớ, checkpoint hỏng...
            _LOAD_ERROR = f"{type(exc).__name__}: {exc}"
            print(f"[LA-3B] Nạp thất bại — {_LOAD_ERROR}")
            return False


def _empty_cache() -> None:
    import gc

    import torch

    gc.collect()
    if config.device() == "mps":
        torch.mps.empty_cache()
    elif config.device() == "cuda":
        torch.cuda.empty_cache()


def crop_to_pil(frame_bgr: np.ndarray, box, size: int = 160, pad: int = 10):
    """Cắt một hộp từ khung hình thành ảnh vuông cho LA-3B.

    Kích thước 160 thay vì 128 để giữ được chi tiết nhỏ như quai ba lô hay gọng kính.
    """
    from PIL import Image

    height, width = frame_bgr.shape[:2]
    x1, y1, x2, y2 = (int(v) for v in box)
    crop = frame_bgr[max(0, y1 - pad):min(height, y2 + pad),
                     max(0, x1 - pad):min(width, x2 + pad)]
    if crop.size == 0:
        return None
    resized = cv2.resize(crop, (size, size))
    return Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))


def _parse_boxes(text: str) -> int:
    """Đếm số hộp LA-3B trả về. Có hộp nghĩa là mô hình thấy vật thể được mô tả."""
    count = 0
    for match in re.finditer(r"<ref>(.*?)</ref>(.*?)(?=<ref>|\Z)", text, re.DOTALL):
        for box in re.finditer(
            r"<box><(\d+)><(\d+)><(\d+)><(\d+)></box>", match.group(2)
        ):
            x1, y1, x2, y2 = (int(v) for v in box.groups())
            if x2 > x1 and y2 > y1:
                count += 1
    return count


def match(crops: list, query: str, temperature: float = 0.15,
          votes: int = 1, batch_size: int = 4, max_new_tokens: int = 32) -> list[bool]:
    """Trả về danh sách True/False: khung cắt nào khớp mô tả `query`.

    `temperature` thấp (gần tham lam) cho quyết định ổn định hơn giữa các lần gọi.
    `votes > 1` chạy lặp và lấy theo đa số, đổi lấy độ trễ tăng tương ứng.
    """
    if not crops:
        return []
    if not _READY and not load():
        # Không nạp được mô hình: giữ lại mọi hộp, hệ thống lùi về hành vi luồng
        # Tiêu chuẩn thay vì lọc sạch và báo không có ai.
        return [True] * len(crops)

    import torch

    tally = [0] * len(crops)
    rounds = max(1, votes)
    # Hai tầng khoá. `_INFER_LOCK` giữ suốt cả lô để hai lời gọi LA-3B không xen kẽ
    # nhau. `config.inference_guard()` là khoá dùng chung với YOLO, chỉ giữ trong từng
    # chunk — nếu ôm cả lô thì mọi camera đứng hình đến khi lọc xong.
    with _INFER_LOCK, torch.inference_mode():
        for _ in range(rounds):
            for start in range(0, len(crops), batch_size):
                chunk = crops[start:start + batch_size]
                try:
                    with config.inference_guard():
                        raws = _generate_batch_hybrid(
                            [(c, query) for c in chunk],
                            temperature=temperature, top_p=0.9,
                            repetition_penalty=1.1, max_new_tokens=max_new_tokens,
                            scheduler="eager", group_size=0,
                        )
                except Exception as exc:
                    print(f"[LA-3B] Lỗi suy luận: {exc}")
                    return [True] * len(crops)
                for offset, raw in enumerate(raws):
                    tally[start + offset] += int(_parse_boxes(raw) > 0)
            with config.inference_guard():
                _empty_cache()

    threshold = rounds / 2
    return [t > threshold for t in tally]
