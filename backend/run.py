#!/usr/bin/env python3
"""Khởi chạy backend VisionOS.

    python run.py                 # chạy bình thường
    python run.py --reload        # tự nạp lại khi sửa mã nguồn
"""
from __future__ import annotations

import argparse

import uvicorn

from app import config

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=config.API_HOST)
    parser.add_argument("--port", type=int, default=config.API_PORT)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    print(f"VisionOS API → http://{args.host}:{args.port}  (thiết bị: {config.device()})")
    print(f"Tài liệu API  → http://localhost:{args.port}/docs")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
