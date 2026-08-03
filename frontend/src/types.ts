/** Kiểu dữ liệu dùng chung, phản ánh đúng lược đồ trả về từ backend. */

export type CameraKind = 'usb' | 'rtsp' | 'file';
export type CameraStatus = 'starting' | 'online' | 'offline' | 'stopped';
export type TaskType = 'counting' | 'zone' | 'detection';

/** Một đỉnh của vùng đa giác, toạ độ chuẩn hoá 0..1. */
export interface ZonePoint {
  x: number;
  y: number;
}
/**
 * standard = đếm mọi đối tượng thuộc nhóm đã chọn.
 * smart    = chỉ đếm đối tượng khớp mô tả tiếng Việt của người dùng.
 */
export type PipelineMode = 'standard' | 'smart';
export type EventStatus = 'new' | 'processing' | 'closed';
export type CountDirection = 'in' | 'out' | 'both';
export type AutoReset = 'never' | 'hourly' | 'daily';

/** Một khung giờ chạy. `days` đánh số 2 = thứ Hai … 8 = Chủ nhật. */
export interface ScheduleSlot {
  days: number[];
  from: string;
  to: string;
}

export interface ScheduleSpec {
  enabled: boolean;
  slots: ScheduleSlot[];
}

/** Một pipeline đang chạy trên camera, kèm số đếm riêng của nó. */
export interface CameraPipeline {
  id: string;
  name: string;
  mode: PipelineMode | null;
  task: TaskType | null;
  in_count: number;
  out_count: number;
  in_zone: number;
  occupancy: number;
}

export interface Camera {
  id: string;
  name: string;
  location: string;
  source: string;
  kind: CameraKind;
  enabled: boolean;
  retention_days: number | null;
  created_at: string;
  /* Trạng thái thời gian thực do backend ghép thêm */
  status: CameraStatus;
  fps: number;
  latency_ms: number;
  resolution: string;
  in_count: number;
  out_count: number;
  occupancy: number;
  /** Của pipeline đầu tiên; dùng `pipelines` khi cần đủ danh sách. */
  pipeline_id: string | null;
  pipeline_name: string | null;
  pipelines: CameraPipeline[];
  error: string | null;
}

export interface LineSpec {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface SmartInfo {
  prompt: string;
  filter_text: string;
  query: string;
  direction: 'in' | 'out' | 'both';
  uses_la: boolean;
}

export interface PromptPreview extends SmartInfo {
  direction_label: string;
  note: string;
}

export interface Pipeline {
  id: string;
  name: string;
  camera_id: string;
  task: TaskType;
  mode: PipelineMode;
  prompt: string | null;
  classes: string[];
  line: LineSpec;
  zone: ZonePoint[];
  flip: boolean;
  conf: number | null;
  direction: CountDirection;
  max_count: number | null;
  auto_reset: AutoReset;
  target_fps: number | null;
  schedule: ScheduleSpec | null;
  in_schedule: boolean;
  schedule_text: string | null;
  active: boolean;
  running: boolean;
  created_at: string;
  in_count: number;
  out_count: number;
  in_zone: number;
  occupancy: number;
  la_calls: number;
  la_matched: number;
  la_rejected: number;
  la_pending: number;
  smart_info: SmartInfo | null;
}

export interface DetectionBox {
  track_id: number;
  label: string;
  confidence: number;
  box: [number, number, number, number];
}

export interface CameraState {
  camera_id: string;
  status: CameraStatus;
  width: number;
  height: number;
  fps: number;
  latency_ms: number;
  frame_idx: number;
  error: string | null;
  pipeline_id: string | null;
  pipeline_name: string | null;
  mode: PipelineMode | null;
  smart_info: SmartInfo | null;
  in_count: number;
  out_count: number;
  in_zone: number;
  occupancy: number;
  detections: DetectionBox[];
  la_calls?: number;
  la_matched?: number;
  la_rejected?: number;
  la_pending?: number;
}

export interface AppEvent {
  id: string;
  ts: string;
  camera_id: string | null;
  camera_name?: string | null;
  pipeline_id: string | null;
  type: string;
  direction: 'in' | 'out' | null;
  label: string | null;
  track_id: number | null;
  snapshot: string | null;
  message: string | null;
  status: EventStatus;
  note: string | null;
  handled_at: string | null;
  offset_seconds?: number;
  clock?: string;
}

export interface Segment {
  id: string;
  camera_id: string;
  start_ts: string;
  end_ts: string | null;
  path: string;
  duration: number;
  available: boolean;
  clock: string;
  offset_seconds: number;
}

export interface TimelineData {
  date: string;
  segments: Segment[];
  events: AppEvent[];
}

export interface SearchResult {
  query: string;
  filters: {
    label: string | null;
    direction: string | null;
    camera_id: string | null;
    from: string | null;
    to: string | null;
    understood: string[];
  };
  total: number;
  results: AppEvent[];
}

export interface CountsSeries {
  series: { bucket: string; key: string; in: number; out: number }[];
  total_in: number;
  total_out: number;
  net: number;
  peak_bucket: string | null;
}

export interface Summary {
  cameras_total: number;
  cameras_enabled: number;
  pipelines_active: number;
  events_today: number;
  in_today: number;
  out_today: number;
  unread_events: number;
}

export interface TaskCatalog {
  /** `counting` gồm cả đếm qua vạch lẫn đếm trong vùng — kiểu hình vẽ quyết định. */
  tasks: {
    id: 'counting' | 'detection'; name: string; description: string;
    needs_shape: boolean; shapes: ('line' | 'polygon')[];
  }[];
  classes: { id: string; name: string }[];
  modes: {
    id: PipelineMode; name: string; description: string;
    hint: string; available: boolean;
  }[];
  directions: { id: CountDirection; name: string; description: string }[];
  auto_resets: { id: AutoReset; name: string }[];
  speed_presets: {
    id: string; name: string; description: string;
    target_fps: number; conf: number; recommended: boolean; bullets: string[];
  }[];
  trackers: { id: string; name: string; available: boolean }[];
  prompt_examples: string[];
  prompt_hint: string;
}

export interface ProbeResult {
  ok: boolean;
  message: string;
  width?: number;
  height?: number;
  fps?: number;
  elapsed_ms?: number;
}
