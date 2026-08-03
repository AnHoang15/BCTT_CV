"""Backend VisionOS — giám sát camera bằng thị giác máy tính."""
import os

# Phải đặt TRƯỚC khi bất kỳ module nào import torch.
# MPS của Apple chưa cài đặt đủ toán tử mà LocateAnything-3B cần; biến này cho phép
# PyTorch tự lùi những toán tử thiếu về CPU thay vì báo lỗi.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

__version__ = "1.1.0"
