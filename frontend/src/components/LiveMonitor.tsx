/**
 * Trang giám sát trực tiếp.
 *
 * Mặc định là lưới camera chiếm toàn bộ chiều ngang, không có thanh cảnh báo cố định.
 * Cảnh báo chỉ hiện khi người dùng bấm phóng to một camera đang chạy pipeline AI, và
 * khi đó chỉ hiện cảnh báo của đúng camera đó. Lý do: danh sách gộp mọi camera trôi
 * rất nhanh, nhìn vào không biết sự kiện thuộc về đâu; còn khi đang xem một camera cụ
 * thể thì cảnh báo của nó mới thật sự có ích.
 *
 * Ảnh trong luồng đã được backend vẽ sẵn hộp giới hạn, vạch đếm và bảng thông tin, nên
 * mọi máy trạm nhìn thấy đúng một kết quả và chi phí xử lý chỉ tốn một lần ở máy chủ.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BellOff, Check, Grid2x2, Grid3x3, LogIn, LogOut, Maximize, Maximize2, Plus, Power,
  RefreshCw, Sparkles, Square, Trash2, X,
} from 'lucide-react';
import * as api from '../api';
import type { AppEvent, Camera } from '../types';
import CameraDialog from './CameraDialog';
import {
  EmptyState, ErrorBanner, Lightbox, StatusDot, StreamImage, formatTimestamp,
  ConfirmDialog, useToast,
} from './common';

type GridSize = 1 | 4 | 9;

interface Props {
  cameras: Camera[];
  onChanged: () => void;
}

export default function LiveMonitor({ cameras, onChanged }: Props) {
  const { toast } = useToast();
  const [grid, setGrid] = useState<GridSize>(4);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  /** Cảnh báo đang xem ảnh phóng to; null là không mở. */
  const [lightbox, setLightbox] = useState<AppEvent | null>(null);
  const [adding, setAdding] = useState(false);
  /** Camera đang chờ xác nhận xoá; null là không mở hộp thoại. */
  const [deleting, setDeleting] = useState<Camera | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);
  // Đổi giá trị này để buộc thẻ <img> mở lại kết nối MJPEG.
  const [streamNonce, setStreamNonce] = useState(() => Date.now());

  /* Toàn màn hình gồm hai lớp:
     1. Lớp trong ứng dụng — khung hình phủ kín cửa sổ trình duyệt bằng `fixed inset-0`.
        Lớp này luôn hoạt động.
     2. Lớp của trình duyệt — gọi thêm Fullscreen API để ẩn cả thanh địa chỉ.
        Trình duyệt chỉ cho gọi khi có thao tác thật của người dùng và một số môi
        trường nhúng chặn hẳn, nên không dựa vào nó để hiển thị đúng. */
  const stageRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    // Người dùng bấm Esc thoát fullscreen của trình duyệt thì thu lớp trong ứng dụng theo.
    const sync = () => {
      if (!document.fullscreenElement) setIsFullscreen(false);
    };
    document.addEventListener('fullscreenchange', sync);
    return () => document.removeEventListener('fullscreenchange', sync);
  }, []);

  useEffect(() => {
    if (!isFullscreen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsFullscreen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isFullscreen]);

  const toggleFullscreen = () => {
    const next = !isFullscreen;
    setIsFullscreen(next);
    // Cố gọi thêm fullscreen của trình duyệt; thất bại thì bỏ qua vì lớp trong ứng
    // dụng đã đủ phủ kín cửa sổ.
    void (next
      ? stageRef.current?.requestFullscreen?.().catch(() => undefined)
      : document.fullscreenElement && document.exitFullscreen().catch(() => undefined));
  };

  const expandedCamera = useMemo(
    () => cameras.find((c) => c.id === expanded) ?? null,
    [cameras, expanded],
  );
  // Chỉ camera đang chạy pipeline mới sinh ra cảnh báo để hiển thị.
  const showAlerts = Boolean(expandedCamera?.pipeline_id);

  const loadEvents = useCallback(async () => {
    if (!expanded || !showAlerts) {
      setEvents([]);
      return;
    }
    try {
      setEvents(await api.listEvents({ camera_id: expanded, limit: 60 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được cảnh báo');
    }
  }, [expanded, showAlerts]);

  useEffect(() => {
    loadEvents();
    if (!expanded) return;
    const timer = window.setInterval(loadEvents, 4000);
    return () => window.clearInterval(timer);
  }, [loadEvents, expanded]);

  const visible = useMemo(
    () => (expanded ? cameras.filter((c) => c.id === expanded) : cameras.slice(0, grid)),
    [cameras, grid, expanded],
  );
  // Không để lại ô trống: hai camera trong lưới 2×2 thì xếp 2 cột cho khung hình to
  // hơn, thay vì bốn ô mà hai ô rỗng.
  const requested = expanded || grid === 1 ? 1 : grid === 4 ? 2 : 3;
  const columns = Math.max(1, Math.min(requested, visible.length));

  const handleAck = async (event: AppEvent, status: 'processing' | 'closed') => {
    try {
      await api.updateEvent(event.id, { status });
      loadEvents();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không cập nhật được cảnh báo');
    }
  };

  const handleToggle = async (camera: Camera) => {
    try {
      await api.toggleCamera(camera.id);
      setStreamNonce(Date.now());
      onChanged();
      toast(camera.enabled ? `Đã tắt camera "${camera.name}"` : `Đã bật camera "${camera.name}"`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không bật/tắt được camera');
      toast(err instanceof Error ? err.message : 'Không bật/tắt được camera', 'error');
    }
  };

  const handleDelete = async (camera: Camera) => {
    setDeletingBusy(true);
    try {
      await api.deleteCamera(camera.id);
      if (expanded === camera.id) setExpanded(null);
      onChanged();
      toast(`Đã xoá camera "${camera.name}" và toàn bộ dữ liệu liên quan`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không xoá được camera');
      toast(err instanceof Error ? err.message : 'Không xoá được camera', 'error');
    } finally {
      setDeletingBusy(false);
      setDeleting(null);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col p-4">
      <header className="mb-3 flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-800">
            {expandedCamera ? expandedCamera.name : 'Giám sát trực tiếp'}
          </h1>
          <p className="text-sm text-slate-500">
            {expandedCamera
              ? expandedCamera.pipeline_name ?? 'Chưa gắn pipeline nào'
              : `${cameras.filter((c) => c.status === 'online').length}/${cameras.length} camera đang phát`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {expanded ? (
            <>
              <button onClick={toggleFullscreen} className="btn-primary">
                <Maximize size={14} />
                {isFullscreen ? 'Thoát toàn màn hình' : 'Toàn màn hình'}
              </button>
              <button onClick={() => setExpanded(null)} className="btn-ghost">
                <X size={14} /> Về lưới camera
              </button>
            </>
          ) : (
            <>
              <button onClick={() => setAdding(true)} className="btn-primary">
                <Plus size={14} /> Thêm camera
              </button>
              <div className="flex items-center gap-0.5 rounded-lg border border-slate-200
                              bg-white p-1">
                {([1, 4, 9] as GridSize[]).map((size) => (
                  <button
                    key={size}
                    onClick={() => setGrid(size)}
                    title={`Lưới ${size === 1 ? '1×1' : size === 4 ? '2×2' : '3×3'}`}
                    className={`cursor-pointer rounded p-1.5 transition-colors ${
                      grid === size
                        ? 'bg-emerald-600 text-white'
                        : 'text-slate-400 hover:bg-slate-100'
                    }`}
                  >
                    {size === 1 ? <Square size={15} />
                      : size === 4 ? <Grid2x2 size={15} />
                      : <Grid3x3 size={15} />}
                  </button>
                ))}
              </div>
            </>
          )}
          <button
            onClick={() => {
              setStreamNonce(Date.now());
              onChanged();
            }}
            className="btn-ghost"
            title="Kết nối lại toàn bộ luồng"
          >
            <RefreshCw size={14} /> Làm mới
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-3 shrink-0">
          <ErrorBanner message={error} onRetry={() => setError(null)} />
        </div>
      )}

      {/* `stageRef` là vùng được đưa vào chế độ toàn màn hình, gồm cả khung hình lẫn
          bảng cảnh báo. Nền trắng để lúc toàn màn hình không lộ nền đen của trình
          duyệt ở hai bên. */}
      <div
        ref={stageRef}
        className={`flex min-h-0 gap-3 bg-neutral-50 ${
          isFullscreen ? 'fixed inset-0 z-50 p-3' : 'flex-1'
        }`}
      >
        {/* ── Danh sách camera ────────────────────────────────────────
            Ẩn khi toàn màn hình để khung hình chiếm hết chỗ. */}
        {!isFullscreen && cameras.length > 0 && (
          <aside className="card flex w-64 shrink-0 flex-col">
            <div className="card-head shrink-0 !py-2">
              <span className="card-head-title">Camera</span>
              <span className="text-xs text-slate-400">{cameras.length}</span>
            </div>
            <div className="scroll-thin min-h-0 flex-1 divide-y divide-slate-100
                            overflow-y-auto">
              {cameras.map((camera) => (
                <button
                  key={camera.id}
                  onClick={() => setExpanded(expanded === camera.id ? null : camera.id)}
                  className={`flex w-full cursor-pointer items-start gap-2 px-3 py-2.5
                              text-left transition-colors ${
                    expanded === camera.id
                      ? 'bg-emerald-50/70'
                      : 'hover:bg-slate-50'
                  }`}
                >
                  <span
                    className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                      !camera.enabled ? 'bg-slate-300'
                        : camera.status === 'online' ? 'bg-emerald-500'
                        : 'bg-rose-500'
                    }`}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-bold text-slate-800">
                      {camera.name}
                    </span>
                    <span className="block truncate text-xs text-slate-500">
                      {camera.location || 'Chưa đặt vị trí'}
                    </span>
                    {camera.pipeline_name && (
                      <span className="mt-0.5 flex items-center gap-1 truncate text-xs
                                       font-medium text-emerald-700">
                        <Sparkles size={10} className="shrink-0" />
                        {camera.pipeline_name}
                      </span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          </aside>
        )}

        {/* ── Lưới camera / camera đang phóng to ──────────────────────── */}
        <div className="relative min-w-0 flex-1">
          {isFullscreen && (
            // Đặt trong cột khung hình, không phải cột cảnh báo, để không che tiêu đề
            // bảng cảnh báo bên phải.
            <button
              onClick={toggleFullscreen}
              className="btn-dark absolute right-3 top-3 z-10"
            >
              <X size={14} /> Thoát toàn màn hình (Esc)
            </button>
          )}
          {cameras.length === 0 ? (
            <div className="card">
              <EmptyState
                icon={<BellOff size={40} />}
                title="Chưa có camera nào"
                hint="Bấm “Thêm camera” ở góc trên để khai báo nguồn video đầu tiên."
              />
            </div>
          ) : (
            <div
              className="grid h-full auto-rows-fr gap-3"
              style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
            >
              {visible.map((camera) => (
                <CameraTile
                  key={camera.id}
                  camera={camera}
                  nonce={streamNonce}
                  expanded={expanded === camera.id}
                  onExpand={() => setExpanded(expanded === camera.id ? null : camera.id)}
                  onToggle={() => handleToggle(camera)}
                  onDelete={() => setDeleting(camera)}
                />
              ))}
            </div>
          )}
        </div>

        {/* ── Cảnh báo của riêng camera đang xem ──────────────────────── */}
        {expandedCamera && showAlerts && (
          <aside className="card flex w-96 shrink-0 flex-col">
            <div className="card-head shrink-0">
              <span className="card-head-title">Cảnh báo camera này</span>
              <span
                className={`badge ${
                  events.some((e) => e.status === 'new')
                    ? 'bg-rose-600 text-white'
                    : 'bg-slate-100 text-slate-500'
                }`}
              >
                {events.filter((e) => e.status === 'new').length} mới
              </span>
            </div>
            <div className="scroll-thin min-h-0 flex-1 divide-y divide-slate-100
                            overflow-y-auto">
              {events.length === 0 ? (
                <EmptyState
                  icon={<BellOff size={30} />}
                  title="Chưa có cảnh báo"
                  hint="Pipeline đang chạy nhưng chưa ghi nhận sự kiện nào."
                />
              ) : (
                events.map((event) => (
                  <EventRow
                    key={event.id}
                    event={event}
                    onAck={handleAck}
                    onOpen={setLightbox}
                  />
                ))
              )}
            </div>
          </aside>
        )}
      </div>

      {adding && (
        <CameraDialog onClose={() => setAdding(false)} onCreated={onChanged} />
      )}

      {deleting && (
        <ConfirmDialog
          title={`Xoá camera "${deleting.name}"?`}
          message="Toàn bộ pipeline, đoạn ghi hình và sự kiện của camera này cũng bị xoá vĩnh viễn. Thao tác này không thể hoàn tác."
          confirmLabel="Xoá vĩnh viễn"
          busy={deletingBusy}
          onConfirm={() => handleDelete(deleting)}
          onCancel={() => !deletingBusy && setDeleting(null)}
        />
      )}

      {lightbox && (
        <Lightbox event={lightbox} onClose={() => setLightbox(null)} />
      )}
    </div>
  );
}

/* ── Ô camera ─────────────────────────────────────────────────────────── */
function CameraTile({
  camera, nonce, expanded, onExpand, onToggle, onDelete,
}: {
  camera: Camera; nonce: number; expanded: boolean;
  onExpand: () => void; onToggle: () => void; onDelete: () => void;
}) {
  const isLive = camera.enabled && camera.status === 'online';
  const pipelines = camera.pipelines ?? [];

  /* Một camera chạy được nhiều pipeline cùng lúc. Vẽ chồng tất cả lên một khung hình
     thì rối, nên mỗi lần chỉ xem một cái và có nút chuyển. Giữ lựa chọn theo mã
     pipeline chứ không theo vị trí, vì danh sách làm mới mỗi bốn giây và thứ tự có
     thể đổi khi bật tắt pipeline khác. */
  const [viewing, setViewing] = useState<string | null>(null);
  const active = pipelines.find((p) => p.id === viewing) ?? pipelines[0] ?? null;

  return (
    <div className="card group flex min-h-0 flex-col">
      {/* Bấm thẳng vào khung hình là mở camera, không cần tìm nút phóng to. Khi đã
          mở rồi thì bỏ hành vi này để bấm vào ảnh không vô tình thoát ra. */}
      <div
        onClick={expanded ? undefined : onExpand}
        role={expanded ? undefined : 'button'}
        tabIndex={expanded ? undefined : 0}
        onKeyDown={(event) => {
          if (!expanded && (event.key === 'Enter' || event.key === ' ')) {
            event.preventDefault();
            onExpand();
          }
        }}
        title={expanded ? undefined : 'Bấm để xem camera này'}
        className={`relative min-h-[14rem] flex-1 bg-slate-950 outline-none ${
          expanded ? '' : 'cursor-pointer focus-visible:ring-2 focus-visible:ring-emerald-500'
        }`}
      >
        {isLive ? (
          <StreamImage
            key={active?.id ?? 'default'}
            src={api.streamUrl(camera.id, `${nonce}-${active?.id ?? ''}`, false, active?.id)}
            alt={camera.name}
            className="absolute inset-0 h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-slate-500">
            <Power size={26} />
            <p className="text-sm font-bold">
              {camera.enabled ? 'Đang kết nối lại…' : 'Camera đã tắt'}
            </p>
            {camera.error && (
              <p className="max-w-[80%] text-center text-xs text-slate-600">
                {camera.error}
              </p>
            )}
          </div>
        )}

        {isLive && active && (
          <div className="absolute bottom-2 right-2 flex gap-1.5">
            {active.task === 'zone' ? (
              <>
                <span className="chip-dark !bg-emerald-600/90" title="Đang trong vùng">
                  <Square size={11} /> {active.in_zone}
                </span>
                <span className="chip-dark !bg-slate-700/90" title="Tổng lượt đã vào">
                  <LogIn size={12} /> {active.in_count}
                </span>
              </>
            ) : (
              <>
                <span className="chip-dark !bg-emerald-600/90" title="Lượt vào">
                  <LogIn size={12} /> {active.in_count}
                </span>
                <span className="chip-dark !bg-rose-600/90" title="Lượt ra">
                  <LogOut size={12} /> {active.out_count}
                </span>
              </>
            )}
          </div>
        )}

        {/* Nút chuyển pipeline, chỉ hiện khi camera có từ hai cái trở lên. */}
        {isLive && pipelines.length > 1 && (
          <div
            onClick={(event) => event.stopPropagation()}
            className="absolute bottom-2 left-2 flex max-w-[70%] flex-wrap gap-1"
          >
            {pipelines.map((pipeline) => (
              <button
                key={pipeline.id}
                onClick={() => setViewing(pipeline.id)}
                title={`Xem kết quả của: ${pipeline.name}`}
                className={`max-w-[11rem] truncate rounded-full px-2 py-0.5 text-xs
                            font-semibold transition-colors ${
                  pipeline.id === active?.id
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-950/70 text-slate-200 hover:bg-slate-950/90'
                }`}
              >
                {pipeline.name}
              </button>
            ))}
          </div>
        )}

        {!expanded && (
          <span className="pointer-events-none absolute inset-x-0 top-0 flex
                           justify-center bg-gradient-to-b from-slate-950/70
                           to-transparent py-2 text-xs font-bold text-white
                           opacity-0 transition-opacity group-hover:opacity-100">
            Bấm để xem camera này
          </span>
        )}
      </div>

      <div className="flex shrink-0 items-center justify-between px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-slate-800">{camera.name}</p>
          <div className="flex items-center gap-2">
            <StatusDot status={camera.enabled ? camera.status : 'stopped'} />
            {isLive && (
              <span className="text-xs text-slate-400">
                {camera.fps} FPS · {camera.resolution}
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            onClick={onToggle}
            className={`btn !px-2 !py-1 ${
              camera.enabled
                ? 'text-slate-400 hover:bg-slate-100'
                : 'text-emerald-600 hover:bg-emerald-50'
            }`}
            title={camera.enabled ? 'Tắt luồng' : 'Bật luồng'}
          >
            <Power size={15} />
          </button>
          <button
            onClick={onDelete}
            className="btn !px-2 !py-1 text-slate-300 hover:bg-rose-50 hover:text-rose-600"
            title="Xoá camera"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {active && (
        <p className="flex shrink-0 items-center gap-1.5 border-t border-slate-100
                      bg-emerald-50/60 px-3 py-1.5 text-xs font-medium text-emerald-700">
          <Sparkles size={12} />
          <span className="truncate">{active.name}</span>
          {pipelines.length > 1 && (
            <span className="ml-auto shrink-0 text-emerald-600/70">
              {pipelines.findIndex((p) => p.id === active.id) + 1}/{pipelines.length}
            </span>
          )}
        </p>
      )}
    </div>
  );
}

/* ── Một dòng cảnh báo ────────────────────────────────────────────────── */
function EventRow({
  event, onAck, onOpen,
}: {
  event: AppEvent;
  onAck: (event: AppEvent, status: 'processing' | 'closed') => void;
  onOpen: (event: AppEvent) => void;
}) {
  const statusStyle: Record<string, string> = {
    new: 'bg-rose-50 text-rose-700 border border-rose-100',
    processing: 'bg-amber-50 text-amber-700 border border-amber-100',
    closed: 'bg-slate-100 text-slate-500 border border-slate-200',
  };
  const statusLabel: Record<string, string> = {
    new: 'Mới', processing: 'Đang xử lý', closed: 'Đã đóng',
  };

  return (
    <div className="flex gap-3 p-3 transition-colors hover:bg-slate-50">
      {event.snapshot ? (
        <button
          onClick={() => onOpen(event)}
          title="Bấm để xem ảnh lớn"
          className="group relative h-16 w-24 shrink-0 cursor-zoom-in overflow-hidden
                     rounded-lg"
        >
          <img
            src={api.eventSnapshotUrl(event.id, 200)}
            alt={event.message ?? 'Ảnh cảnh báo'}
            loading="lazy"
            className="h-full w-full object-cover"
          />
          <span className="absolute inset-0 flex items-center justify-center bg-slate-950/50
                           opacity-0 transition-opacity group-hover:opacity-100">
            <Maximize2 size={14} className="text-white" />
          </span>
        </button>
      ) : (
        <div className="flex h-16 w-24 shrink-0 items-center justify-center rounded-lg
                        bg-slate-100 text-xs text-slate-400">
          không có ảnh
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-bold text-slate-800">{event.message ?? event.type}</p>
          <span className={`badge shrink-0 ${statusStyle[event.status]}`}>
            {statusLabel[event.status]}
          </span>
        </div>
        <p className="mt-0.5 text-xs text-slate-500">{formatTimestamp(event.ts)}</p>

        {event.status !== 'closed' && (
          <div className="mt-1.5 flex gap-1.5">
            {event.status === 'new' && (
              <button
                onClick={() => onAck(event, 'processing')}
                className="btn-ghost !px-2 !py-0.5 !text-xs"
              >
                <Check size={11} /> Xác nhận
              </button>
            )}
            <button
              onClick={() => onAck(event, 'closed')}
              className="btn-ghost !px-2 !py-0.5 !text-xs"
            >
              <X size={11} /> Đóng
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
