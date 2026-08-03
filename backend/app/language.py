"""Xử lý câu lệnh tiếng Việt cho luồng Thông minh.

Hai việc: tách câu lệnh thành (thuộc tính cần lọc, chiều cần đếm), và dịch phần thuộc
tính sang tiếng Anh trước khi đưa vào LocateAnything-3B.

Lý do phải dịch: LA-3B huấn luyện chủ yếu trên tiếng Anh và tiếng Trung nên không hiểu
tiếng Việt. Đưa thẳng "người đeo ba lô" vào thì mô hình giữ lại gần như mọi khung cắt,
tức là không lọc gì cả; bản tiếng Anh "person with backpack" mới lọc đúng.
"""
from __future__ import annotations

import re
import threading

from . import config

# ── Từ khoá chiều đi và hành động ────────────────────────────────────────────
_DIR_IN = ["đi vào trong", "đi vào", "đi vô", "vào trong", "vào", "vô",
           "entering", "enter", "incoming", "coming in", "go in"]
_DIR_OUT = ["đi ra ngoài", "đi ra", "ra ngoài", "ra", "rời khỏi",
            "exiting", "exit", "leaving", "leave", "outgoing", "going out"]
_ACTION = ["đếm số lượng", "đếm số", "đếm", "số lượng", "số người", "phát hiện",
           "nhận diện", "tìm", "count the number of", "how many", "number of", "count"]

# ── Từ điển vật thể hay dùng ─────────────────────────────────────────────────
# Opus-MT dịch sai một số từ ngắn (chẳng hạn "ô" thành "pane"), nên chốt cứng ở đây.
#
# QUAN TRỌNG — vế phải luôn là VẬT THỂ TRẦN, không bao giờ là "person with X".
# Đo thực tế trên một khung hình 37 người ở sảnh nhà ga:
#
#     truy vấn                   giữ lại
#     person                     36/37   (nền, đúng)
#     person with bag            35/37   ← gần như không lọc gì
#     person carrying a bag      33/37   ← cũng vậy
#     backpack                    9/37   ← lọc thật
#     handbag                    14/37   ← lọc thật
#
# Khi câu bắt đầu bằng "person", mô hình bám vào chữ "person" và gần như bỏ qua vế
# mô tả phía sau. Đưa thẳng vật thể thì nó mới thực sự đi tìm vật thể đó.
_VI_EN: dict[str, str] = {
    "ba lô": "backpack", "balo": "backpack", "ba-lô": "backpack",
    "vali": "suitcase", "va li": "suitcase", "vali kéo": "suitcase",
    "ô": "umbrella", "cái ô": "umbrella", "dù": "umbrella",
    "mũ": "hat", "nón": "hat", "mũ bảo hiểm": "helmet", "mũ bảo hộ": "helmet",
    "kính": "glasses", "khẩu trang": "face mask", "túi xách": "handbag",
    "áo đỏ": "red shirt", "áo trắng": "white shirt", "áo đen": "black shirt",
    "áo xanh": "blue shirt", "áo vàng": "yellow shirt", "áo khoác": "jacket",
    "xe đạp": "bicycle", "xe đẩy": "stroller", "xe đẩy em bé": "stroller",
    "điện thoại": "phone", "laptop": "laptop",
    "túi": "bag", "cặp": "briefcase", "cặp sách": "backpack",
    # Cụm đầy đủ — ưu tiên khớp trước các từ đơn ở trên. Vế phải vẫn là vật thể trần.
    "người đeo ba lô": "backpack",
    "người mang ba lô": "backpack",
    "người đeo túi": "bag",
    "người xách túi": "handbag",
    "người cầm ô": "umbrella",
    "người cầm vali": "suitcase",
    "người đội mũ": "hat",
    "người đội mũ bảo hiểm": "helmet",
    "người mặc áo đỏ": "red shirt",
    "người mặc áo trắng": "white shirt",
    "người mặc áo đen": "black shirt",
    "người mặc áo xanh": "blue shirt",
    "người cầm điện thoại": "phone",
    "người đeo kính": "glasses",
    "người đeo khẩu trang": "face mask",
    # Nhóm mô tả chính con người thì giữ nguyên danh từ chỉ người — ở đây không có
    # vật thể nào để bám vào.
    "trẻ em": "child", "trẻ con": "child", "em bé": "baby",
    "phụ nữ": "woman", "đàn ông": "man", "người già": "elderly person",
}

_VI_CHARS = ("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
             "òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")

# Câu hỏi đơn giản chỉ là "người" thì không cần LA — YOLO đã làm được.
SIMPLE_QUERIES = {"person", "people", "pedestrian", "human",
                  "người", "con người", "mọi người", "tất cả người"}

_MT: dict[str, object] = {"tok": None, "mdl": None}
_MT_LOCK = threading.Lock()
_MT_FILLERS = ("oh, ", "well, ", "hey, ", "so, ", "yeah, ", "oh ", "well ")
_CACHE: dict[str, str] = {}


def has_vietnamese(text: str) -> bool:
    return any(ch in _VI_CHARS for ch in text.lower())


def parse_command(prompt: str) -> tuple[str, str]:
    """Tách câu lệnh thành (thuộc tính cần lọc, chiều đếm).

    "đếm người mặc áo đỏ đi vào"  ->  ("người mặc áo đỏ", "in")
    "ba lô đi ra"                 ->  ("ba lô", "out")
    "người đeo kính"              ->  ("người đeo kính", "both")
    """
    padded = f" {prompt.lower().strip()} "

    def hit(keywords: list[str]) -> bool:
        return any(f" {k} " in padded for k in keywords)

    has_in, has_out = hit(_DIR_IN), hit(_DIR_OUT)
    if has_in and not has_out:
        direction = "in"
    elif has_out and not has_in:
        direction = "out"
    else:
        direction = "both"

    remainder = padded
    for word in sorted(_ACTION + _DIR_IN + _DIR_OUT, key=len, reverse=True):
        remainder = re.sub(rf"(?<=\s){re.escape(word)}(?=\s)", " ", remainder)
    remainder = " ".join(remainder.split()).strip()
    return (remainder or "person"), direction


def _load_translator():
    """Nạp Opus-MT theo kiểu lazy. Chỉ tải khi thật sự gặp prompt tiếng Việt."""
    if _MT["mdl"] is not None:
        return
    from transformers import MarianMTModel, MarianTokenizer

    name = "Helsinki-NLP/opus-mt-vi-en"
    try:
        _MT["tok"] = MarianTokenizer.from_pretrained(name)
        model = MarianMTModel.from_pretrained(name)
    except OSError:
        # Không có mạng: dùng bản đã tải sẵn trong bộ nhớ đệm của HuggingFace.
        _MT["tok"] = MarianTokenizer.from_pretrained(name, local_files_only=True)
        model = MarianMTModel.from_pretrained(name, local_files_only=True)
    # Đẩy lên GPU là thao tác chạm Metal, phải xếp hàng cùng YOLO và LA-3B.
    with config.inference_guard():
        _MT["mdl"] = model.to(config.device()).eval()


def vi_to_en(text: str) -> str:
    """Dịch một cụm tiếng Việt sang tiếng Anh cho LA-3B.

    Ưu tiên từ điển chốt cứng, sau đó mới đến mô hình dịch. Kết quả được nhớ lại nên
    mỗi prompt chỉ dịch đúng một lần, không ảnh hưởng tốc độ xử lý khung hình.
    """
    key = text.strip().lower()
    if not key:
        return "person"
    if key in _CACHE:
        return _CACHE[key]
    if key in _VI_EN:
        _CACHE[key] = _VI_EN[key]
        return _VI_EN[key]

    # Câu dài chứa vật thể đã biết: lấy thẳng vật thể ra thay vì gọi mô hình dịch.
    # Bản dịch tự do hay thêm chủ ngữ ("the man with the bag") mà chủ ngữ chính là
    # thứ làm mô hình bỏ qua vế mô tả.
    found = sorted(((k, v) for k, v in _VI_EN.items() if k in key),
                   key=lambda kv: -len(kv[0]))
    if found:
        objects: list[str] = []
        for k, v in found:
            # Bỏ từ ngắn nếu đã có cụm dài hơn chứa nó.
            if not any(k != other and k in other for other, _ in found):
                objects.append(v)
        if objects:
            # Nhiều vật thể thì nối bằng dấu phân cách của LA, mỗi vế vẫn là vật thể
            # trần chứ không gộp thành một câu có chủ ngữ.
            result = "</c>".join(dict.fromkeys(objects))
            _CACHE[key] = result
            return result

    with _MT_LOCK:
        _load_translator()
        import torch

        tok, mdl = _MT["tok"], _MT["mdl"]
        batch = tok([text], return_tensors="pt", padding=True, truncation=True)
        with config.inference_guard():
            batch = {k: v.to(mdl.device) for k, v in batch.items()}
            with torch.no_grad():
                generated = mdl.generate(**batch, max_new_tokens=40, num_beams=4)
        out = tok.decode(generated[0], skip_special_tokens=True)

    out = out.strip().lower().rstrip(" .!?,")
    for filler in _MT_FILLERS:
        if out.startswith(filler):
            out = out[len(filler):]
    out = _strip_subject(out.strip()) or "person"
    _CACHE[key] = out
    return out


# Bản dịch tự do hay ra "the man with the bag". Chủ ngữ đứng đầu chính là thứ khiến mô
# hình bám vào "người" và bỏ qua vế mô tả, nên cắt bỏ để còn lại vật thể trần.
_SUBJECT_PREFIX = re.compile(
    r"^(?:the|a|an)?\s*(?:man|woman|person|people|guy|girl|boy|lady|someone)\s+"
    r"(?:with|wearing|carrying|holding|in|who\s+has|that\s+has)\s+(?:the|a|an)?\s*",
)


def _strip_subject(text: str) -> str:
    stripped = _SUBJECT_PREFIX.sub("", text).strip()
    # Chỉ nhận nếu còn lại thứ gì đó có nghĩa; cắt cụt thành chuỗi rỗng thì giữ bản cũ.
    return stripped if len(stripped) >= 2 else text


def build_query(filter_text: str) -> str:
    """Chuyển phần thuộc tính thành truy vấn cho LA-3B.

    Dấu phẩy tách nhiều nhóm đối tượng; LA-3B dùng `</c>` làm dấu phân cách.
    """
    parts = [p.strip() for p in filter_text.split(",") if p.strip()]
    if not parts:
        return "person"
    translated = [vi_to_en(p) if has_vietnamese(p) else p for p in parts]
    return "</c>".join(translated)


def is_simple(query: str) -> bool:
    """Truy vấn chỉ là 'người' thì bỏ qua LA cho nhanh."""
    return query.split("</c>")[0].strip().lower() in SIMPLE_QUERIES


def describe(prompt: str) -> dict:
    """Diễn giải câu lệnh để hiển thị lại cho người dùng."""
    filter_text, direction = parse_command(prompt)
    query = build_query(filter_text)
    return {
        "prompt": prompt,
        "filter_text": filter_text,
        "query": query,
        "direction": direction,
        "uses_la": not is_simple(query),
    }
