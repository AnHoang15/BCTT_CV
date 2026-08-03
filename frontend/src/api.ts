/**
 * Lớp gọi API.
 *
 * Mọi đường dẫn đều tương đối (`/api/...`): khi phát triển, Vite chuyển tiếp sang
 * backend theo cấu hình proxy; khi triển khai, frontend và backend nằm cùng một tên
 * miền nên không cần sửa gì.
 */
import type {
  AppEvent, AutoReset, Camera, CameraState, CountDirection, CountsSeries, LineSpec,
  Pipeline, PipelineMode, ProbeResult, PromptPreview, ScheduleSpec, SearchResult,
  Summary, TaskCatalog, TaskType, TimelineData, ZonePoint,
} from './types';

// const BASE = '/api';
const API_ORIGIN = import.meta.env.VITE_API_URL ?? "";
const BASE = `${API_ORIGIN}/api`;
/**
 * Thời gian chờ tối đa cho một lời gọi API.
 *
 * Không có mốc này thì một yêu cầu treo sẽ treo vĩnh viễn: `fetch` không tự bỏ cuộc.
 * Tình huống thật gặp phải là backend chưa sẵn sàng — proxy của Vite giữ kết nối chờ
 * chứ không báo lỗi, nên trang cấu hình quay vòng xoay mãi mà không bao giờ hiện được
 * nút thử lại. Mười lăm giây đủ rộng cho lần gọi chậm nhất (danh mục bài toán mất
 * chưa tới 5 ms, tìm kiếm nặng nhất cũng dưới một giây).
 */
const TIMEOUT_MS = 15_000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
      signal: controller.signal,
      ...init,
    });
  } catch (err) {
    // Phân biệt hai nguyên nhân, vì cách xử lý của người dùng khác nhau: hết giờ chờ
    // thường là backend đang khởi động, còn lỗi mạng là backend chưa chạy hẳn.
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error(
        `Máy chủ không phản hồi sau ${TIMEOUT_MS / 1000} giây. `
        + 'Kiểm tra backend đã chạy chưa rồi thử lại.',
      );
    }
    throw new Error('Không kết nối được tới máy chủ. Kiểm tra backend đã chạy chưa.');
  } finally {
    window.clearTimeout(timer);
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* phản hồi không phải JSON — giữ nguyên thông báo mặc định */
    }
    throw new Error(detail);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/* ── Camera ─────────────────────────────────────────────────────────────── */
export const listCameras = () => request<Camera[]>('/cameras');

export const createCamera = (payload: {
  name: string; source: string; location?: string; kind?: string; enabled?: boolean;
}) => request<Camera>('/cameras', { method: 'POST', body: JSON.stringify(payload) });

export const updateCamera = (id: string, payload: Partial<Camera>) =>
  request<Camera>(`/cameras/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });

export const deleteCamera = (id: string) =>
  request<void>(`/cameras/${id}`, { method: 'DELETE' });

export const toggleCamera = (id: string) =>
  request<Camera>(`/cameras/${id}/toggle`, { method: 'POST' });

export const probeSource = (source: string) =>
  request<ProbeResult>('/cameras/probe', {
    method: 'POST',
    body: JSON.stringify({ source }),
  });

export const getCameraState = (id: string) => request<CameraState>(`/cameras/${id}/state`);

/**
 * URL luồng MJPEG và ảnh tĩnh của camera.
 *
 * `nonce` để trình duyệt không dùng lại kết nối hay ảnh trong bộ nhớ đệm.
 * `raw` lấy khung hình chưa vẽ gì lên — dùng ở màn cấu hình, nơi hộp giới hạn và vạch
 * đếm của pipeline đang chạy chỉ gây nhiễu cho việc vẽ vạch mới.
 */
/**
 * Địa chỉ gốc riêng cho luồng video, tách khỏi địa chỉ gọi API.
 *
 * HTTP/1.1 chỉ cho mở sáu kết nối đồng thời tới mỗi **tên miền**, và hạn mức đó tính
 * chung cho cả trình duyệt chứ không riêng từng tab. Luồng MJPEG là kết nối sống mãi:
 * lưới bốn camera đã ăn bốn chỗ, mở thêm một tab nữa là hết sạch và mọi lời gọi API
 * nằm xếp hàng cho tới khi hết giờ chờ.
 *
 * Cho luồng đi thẳng tới backend thì nó dùng hạn mức của cổng 8000, còn hạn mức của
 * cổng 3000 dành trọn cho API — hai bên không tranh nhau nữa. Backend đã bật CORS nên
 * gọi chéo nguồn không vướng gì.
 *
 * Chỉ áp dụng khi chạy phát triển. Bản dựng để triển khai do chính backend phục vụ nên
 * cùng một tên miền, không tách được mà cũng không cần.
 *
 * Lấy tên máy từ địa chỉ đang mở chứ không ghim cứng `localhost`: mở giao diện bằng
 * `127.0.0.1` hay bằng địa chỉ IP trong mạng nội bộ thì `localhost` sẽ trỏ về đúng máy
 * của người xem chứ không phải máy chạy backend, và mọi ô camera đen thui.
 */
const STREAM_PORT = 8000;
const STREAM_ORIGIN = import.meta.env.DEV
  ? (import.meta.env.VITE_STREAM_ORIGIN
     ?? `${window.location.protocol}//${window.location.hostname}:${STREAM_PORT}`)
  : '';

const frameUrl = (kind: 'stream' | 'snapshot') =>
  (id: string, nonce?: number | string, raw = false, pipelineId?: string | null) => {
    const query = new URLSearchParams();
    if (nonce !== undefined) query.set('t', String(nonce));
    if (raw) query.set('raw', '1');
    // Một camera chạy được nhiều pipeline, mỗi cái vẽ một kiểu lên khung hình.
    // Không nêu rõ thì backend trả bản của pipeline đầu tiên.
    if (pipelineId) query.set('pipeline_id', pipelineId);
    const suffix = query.toString();
    return `${STREAM_ORIGIN}${BASE}/cameras/${id}/${kind}${suffix ? `?${suffix}` : ''}`;
  };

export const streamUrl = frameUrl('stream');
export const snapshotUrl = frameUrl('snapshot');

/* ── Pipeline ───────────────────────────────────────────────────────────── */
export const listPipelines = (cameraId?: string) =>
  request<Pipeline[]>(`/pipelines${cameraId ? `?camera_id=${cameraId}` : ''}`);

export const getTaskCatalog = () => request<TaskCatalog>('/pipelines/tasks');

export const createPipeline = (payload: {
  name: string; camera_id: string; task: TaskType; classes: string[];
  mode?: PipelineMode; prompt?: string | null;
  line?: LineSpec; zone?: ZonePoint[]; flip?: boolean; conf?: number | null;
  direction?: CountDirection; max_count?: number | null;
  auto_reset?: AutoReset; target_fps?: number | null;
  schedule?: ScheduleSpec | null;
}) => request<Pipeline>('/pipelines', { method: 'POST', body: JSON.stringify(payload) });

/** Xem hệ thống hiểu câu lệnh tiếng Việt ra sao trước khi chạy pipeline. */
export const previewPrompt = (prompt: string) =>
  request<PromptPreview>('/pipelines/preview-prompt', {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  });

export const updatePipeline = (id: string, payload: Partial<Pipeline>) =>
  request<Pipeline>(`/pipelines/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });

export const deletePipeline = (id: string) =>
  request<void>(`/pipelines/${id}`, { method: 'DELETE' });

export const startPipeline = (id: string) =>
  request<Pipeline>(`/pipelines/${id}/start`, { method: 'POST' });

export const stopPipeline = (id: string) =>
  request<Pipeline>(`/pipelines/${id}/stop`, { method: 'POST' });

export const resetPipeline = (id: string) =>
  request<Pipeline>(`/pipelines/${id}/reset`, { method: 'POST' });

/* ── Sự kiện, thống kê, tìm kiếm ────────────────────────────────────────── */
export const listEvents = (params: Record<string, string | number | undefined> = {}) => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value));
  });
  return request<AppEvent[]>(`/events?${query.toString()}`);
};

export const updateEvent = (id: string, payload: { status?: string; note?: string }) =>
  request<AppEvent>(`/events/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });

/** Ảnh sự kiện. Truyền `width` để lấy bản thu nhỏ — ảnh gốc từ camera 4K rất nặng. */
export const eventSnapshotUrl = (id: string, width?: number) =>
  `${BASE}/events/${id}/snapshot${width ? `?w=${width}` : ''}`;

export const searchEvents = (q: string) =>
  request<SearchResult>(`/search?q=${encodeURIComponent(q)}`);

export const getCounts = (params: { pipeline_id?: string; camera_id?: string; hours?: number }) => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) query.set(key, String(value));
  });
  return request<CountsSeries>(`/counts?${query.toString()}`);
};

export const getSummary = () => request<Summary>('/summary');

/* ── Xem lại ────────────────────────────────────────────────────────────── */
export const getTimeline = (cameraId: string, date?: string) =>
  request<TimelineData>(
    `/playback/timeline?camera_id=${cameraId}${date ? `&date=${date}` : ''}`,
  );

export const getRecordedDates = (cameraId: string) =>
  request<string[]>(`/playback/dates?camera_id=${cameraId}`);

export const segmentVideoUrl = (segmentId: string) =>
  `${BASE}/playback/segments/${segmentId}/video`;

export const findSegmentAt = (cameraId: string, ts: string) =>
  request<{ segment: { id: string; start_ts: string; duration: number }; seek_seconds: number }>(
    `/playback/at?camera_id=${cameraId}&ts=${encodeURIComponent(ts)}`,
  );
