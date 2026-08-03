"""Lược đồ dữ liệu vào/ra của API (Pydantic)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LineSpec(BaseModel):
    """Toạ độ vạch đếm, chuẩn hoá về 0..1 để không phụ thuộc độ phân giải camera."""
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)


class ZonePoint(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ScheduleSlot(BaseModel):
    """Một khung giờ chạy. `days` đánh số 2=thứ Hai ... 8=Chủ nhật."""
    days: list[int] = Field(min_length=1)
    from_: str = Field(alias="from", pattern=r"^\d{1,2}:\d{2}$")
    to: str = Field(pattern=r"^\d{1,2}:\d{2}$")

    model_config = {"populate_by_name": True}


class ScheduleSpec(BaseModel):
    enabled: bool = False
    slots: list[ScheduleSlot] = []


class CameraIn(BaseModel):
    name: str
    source: str
    location: str = ""
    kind: Literal["usb", "rtsp", "file"] = "usb"
    enabled: bool = True
    retention_days: int | None = None


class CameraUpdate(BaseModel):
    name: str | None = None
    source: str | None = None
    location: str | None = None
    kind: Literal["usb", "rtsp", "file"] | None = None
    enabled: bool | None = None
    retention_days: int | None = None


class ProbeIn(BaseModel):
    source: str


class PipelineIn(BaseModel):
    name: str
    camera_id: str
    # counting = đếm lượt qua vạch; zone = đếm trong vùng đa giác; detection = chỉ nhận diện
    task: Literal["counting", "zone", "detection"] = "counting"
    # standard = chỉ YOLO; smart = YOLO đề xuất, LocateAnything-3B lọc theo mô tả.
    mode: Literal["standard", "smart"] = "standard"
    prompt: str | None = None
    classes: list[str] = ["person"]
    line: LineSpec | None = None
    zone: list[ZonePoint] | None = None
    flip: bool = False
    conf: float | None = Field(default=None, ge=0.01, le=0.95)
    # Chiều cần đếm. Ở chế độ Thông minh, câu lệnh tiếng Việt có thể ghi đè giá trị này.
    direction: Literal["in", "out", "both"] = "both"
    # Cảnh báo khi số đối tượng trong khung (hoặc trong vùng) vượt ngưỡng. None = tắt.
    max_count: int | None = Field(default=None, ge=1, le=999)
    auto_reset: Literal["never", "hourly", "daily"] = "never"
    target_fps: float | None = Field(default=None, ge=1, le=60)
    schedule: ScheduleSpec | None = None


class PipelineUpdate(BaseModel):
    name: str | None = None
    task: Literal["counting", "zone", "detection"] | None = None
    mode: Literal["standard", "smart"] | None = None
    prompt: str | None = None
    classes: list[str] | None = None
    line: LineSpec | None = None
    zone: list[ZonePoint] | None = None
    flip: bool | None = None
    conf: float | None = Field(default=None, ge=0.01, le=0.95)
    direction: Literal["in", "out", "both"] | None = None
    max_count: int | None = Field(default=None, ge=1, le=999)
    auto_reset: Literal["never", "hourly", "daily"] | None = None
    target_fps: float | None = Field(default=None, ge=1, le=60)
    schedule: ScheduleSpec | None = None


class PromptPreview(BaseModel):
    prompt: str


class EventUpdate(BaseModel):
    status: Literal["new", "processing", "closed"] | None = None
    note: str | None = None


class SettingsUpdate(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=365)
    record_enabled: bool | None = None
    yolo_conf: float | None = Field(default=None, ge=0.01, le=0.95)
    target_fps: float | None = Field(default=None, ge=1, le=60)
