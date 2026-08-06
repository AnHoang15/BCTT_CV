/** Các thành phần giao diện nhỏ dùng lại ở nhiều trang. */
import { AlertTriangle, CheckCircle2, Loader2, Play, X, XCircle } from 'lucide-react';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import * as api from '../api';
import type { AppEvent, CameraStatus } from '../types';

/* ── Thông báo nhanh (toast) ─────────────────────────────────────────────
   Dùng để xác nhận hành động thành công/thất bại mà không cắt ngang thao tác
   bằng một hộp thoại. Mỗi toast tự biến mất sau vài giây. */
type ToastTone = 'success' | 'error' | 'info';

interface ToastItem {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastContextValue {
  toast: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => undefined });

export function useToast() {
  return useContext(ToastContext);
}

const TOAST_STYLES: Record<ToastTone, { icon: ReactNode; classes: string }> = {
  success: {
    icon: <CheckCircle2 size={16} />,
    classes: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  },
  error: {
    icon: <XCircle size={16} />,
    classes: 'border-rose-200 bg-rose-50 text-rose-800',
  },
  info: {
    icon: <AlertTriangle size={16} />,
    classes: 'border-sky-200 bg-sky-50 text-sky-800',
  },
};

let toastSeq = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback((message: string, tone: ToastTone = 'success') => {
    const id = ++toastSeq;
    setItems((current) => [...current.slice(-4), { id, tone, message }]);
    timers.current.set(id, setTimeout(() => dismiss(id), 3500));
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* Hiển thị ở góc phải trên, phía dưới thanh điều hướng để không che nút thao tác. */}
      <div className="pointer-events-none fixed right-4 top-[4.5rem] z-[100] flex
                      w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {items.map((item) => {
          const style = TOAST_STYLES[item.tone];
          return (
            <div
              key={item.id}
              role="status"
              className={`pointer-events-auto flex items-start gap-2 rounded-xl border
                          px-3 py-2.5 text-sm font-medium shadow-lg shadow-slate-900/10
                          animate-[toast-in_0.2s_ease-out] ${style.classes}`}
            >
              <span className="mt-0.5 shrink-0">{style.icon}</span>
              <span className="min-w-0 flex-1 break-words">{item.message}</span>
              <button
                onClick={() => dismiss(item.id)}
                className="shrink-0 cursor-pointer rounded p-0.5 opacity-50
                           transition-opacity hover:opacity-100"
                aria-label="Đóng thông báo"
              >
                <X size={13} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function StatusDot({ status, dark = false }: { status: CameraStatus; dark?: boolean }) {
  const map: Record<CameraStatus, { dot: string; label: string }> = {
    online: { dot: 'bg-emerald-500', label: 'Trực tuyến' },
    starting: { dot: 'bg-amber-400', label: 'Đang kết nối' },
    offline: { dot: 'bg-rose-500', label: 'Mất kết nối' },
    stopped: { dot: 'bg-slate-400', label: 'Đã tắt' },
  };
  const item = map[status] ?? map.stopped;
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-medium ${
        dark ? 'text-slate-300' : 'text-slate-500'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${item.dot}`} />
      {item.label}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <Loader2 size={16} className="animate-spin" />
      {label ?? 'Đang tải…'}
    </div>
  );
}

/** Skeleton loading placeholder cho các danh sách và grid. */
export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`rounded-xl border border-slate-200/60 bg-white p-3 shadow-sm ${className}`}>
      <div className="skeleton mb-3 h-4 w-1/3 rounded" />
      <div className="skeleton mb-2 h-3 w-2/3 rounded" />
      <div className="skeleton h-3 w-1/2 rounded" />
    </div>
  );
}

export function SkeletonGrid({ count = 4, className = '' }: { count?: number; className?: string }) {
  return (
    <div className={`grid gap-3 ${className}`} style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-rose-100 bg-rose-50
                    p-3 text-sm text-rose-800">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" />
      <div className="flex-1">
        <p className="font-bold">Không thực hiện được</p>
        <p className="mt-0.5 break-words text-xs">{message}</p>
      </div>
      {onRetry && (
        <button onClick={onRetry} className="btn-ghost shrink-0 !py-1">
          Thử lại
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  icon, title, hint,
}: {
  icon: ReactNode; title: string; hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="text-slate-300">{icon}</div>
      <p className="text-sm font-bold text-slate-600">{title}</p>
      {hint && <p className="max-w-sm text-xs leading-relaxed text-slate-400">{hint}</p>}
    </div>
  );
}

export function Stat({
  label, value, tone = 'slate',
}: {
  label: string; value: string | number;
  tone?: 'slate' | 'emerald' | 'sky' | 'rose' | 'amber';
}) {
  const tones = {
    slate: 'text-slate-800', emerald: 'text-emerald-600', sky: 'text-sky-600',
    rose: 'text-rose-600', amber: 'text-amber-600',
  };
  return (
    <div className="rounded-xl border border-slate-200/80 bg-slate-50 px-3 py-2 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-0.5 text-xl font-bold tabular-nums ${tones[tone]}`}>{value}</p>
    </div>
  );
}

/** Định dạng dung lượng theo đơn vị dễ đọc. */
export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** exponent).toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

/** '2026-07-29T14:03:11' -> '29/07 14:03:11' */
export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)} ${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}:${pad(date.getSeconds())}`;
}

export function todayISO(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * Ảnh nhận luồng MJPEG, tự đóng kết nối khi bị gỡ khỏi giao diện.
 *
 * Gỡ một thẻ `<img>` khỏi DOM **không** làm trình duyệt đóng kết nối MJPEG: nó là
 * phản hồi không bao giờ kết thúc, và trình duyệt giữ socket lại. Phía máy chủ vì thế
 * cũng không biết người xem đã bỏ đi.
 *
 * Hậu quả tích luỹ rất nhanh. HTTP/1.1 chỉ cho mở sáu kết nối đồng thời tới mỗi tên
 * miền; chuyển qua lại giữa các trang vài lần là sáu chỗ đó bị luồng chết chiếm hết,
 * và mọi lời gọi API sau đó nằm xếp hàng cho tới khi hết giờ chờ. Triệu chứng nhìn
 * thấy là giao diện báo máy chủ không phản hồi trong khi máy chủ vẫn trả lời `curl`
 * trong vài mili giây.
 *
 * Cách chữa là gán `src` rỗng trước khi thành phần biến mất — đó là tín hiệu duy nhất
 * khiến trình duyệt thật sự huỷ yêu cầu đang chạy.
 */
/**
 * Ảnh GIF 1×1 trong suốt, dùng làm tín hiệu huỷ luồng.
 *
 * Gán `src` rỗng thì Chromium huỷ yêu cầu đang chạy, nhưng **WebKit thì không** — nó
 * giữ nguyên kết nối `multipart/x-mixed-replace`. Hậu quả trên Safari: mỗi lần chuyển
 * trang là vài kết nối chết nằm lại, tích đủ sáu cái là mọi luồng mới đều đen và không
 * còn cách nào hồi ngoài đóng tab.
 *
 * Gán một ảnh `data:` thì mọi nhân trình duyệt đều phải bắt đầu tải thứ khác, và chính
 * việc đó mới thật sự huỷ yêu cầu cũ. Ảnh nằm ngay trong chuỗi nên không phát sinh
 * thêm lượt gọi mạng nào.
 */
const BLANK_IMAGE =
  'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

export function StreamImage(
  props: React.ImgHTMLAttributes<HTMLImageElement> & { src: string },
) {
  const { src, onError, ...rest } = props;
  const ref = useRef<HTMLImageElement>(null);
  /**
   * Đã phải lùi về đường proxy hay chưa.
   *
   * Luồng đi thẳng tới backend để không tranh hạn mức kết nối với các lời gọi API,
   * nhưng đường đó có thể không tới được — backend nghe cổng khác, hoặc máy chủ chặn
   * gọi chéo nguồn. Khi ấy lùi về đường proxy: chậm hơn về mặt hạn mức nhưng vẫn xem
   * được, hơn hẳn một ô đen không nói gì.
   */
  const [fallback, setFallback] = useState(false);
  /**
   * Ô có nằm trong tầm nhìn không. Ngoài tầm nhìn thì ngắt luồng để trả lại chỗ trong
   * hạn mức sáu kết nối của trình duyệt.
   *
   * Cố ý **không** gắn thêm điều kiện "tab đang hiện". Tôi đã thử và phải bỏ: một số
   * môi trường báo `visibilityState` là "hidden" ngay cả khi trang đang hiển thị thật,
   * và khi đó camera đen mà không có cách nào hồi lại. Giữ đúng một điều kiện quan sát
   * được chắc chắn thì an toàn hơn.
   *
   * Khởi tạo là `true` để hỏng về phía an toàn: nếu `IntersectionObserver` vì lý do gì
   * không chạy, luồng vẫn phát bình thường thay vì đen.
   */
  const [wanted, setWanted] = useState(true);

  useEffect(() => {
    setFallback(false);
  }, [src]);

  useEffect(() => {
    const img = ref.current;
    if (!img) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => setWanted(entry.isIntersecting),
      { threshold: 0.01 },
    );
    observer.observe(img);
    return () => observer.disconnect();
  }, []);

  const target = !wanted
    ? BLANK_IMAGE
    : fallback ? src.replace(/^https?:\/\/[^/]+/, '') : src;

  useEffect(() => {
    const img = ref.current;
    if (!img) return undefined;
    // Quản lý `src` hoàn toàn ở đây chứ không giao cho React: StrictMode ở chế độ phát
    // triển chạy effect hai lần, lần dọn giả sẽ đổi mất `src` mà React không biết để
    // đặt lại. Gỡ thẻ khỏi DOM cũng không đủ để đóng kết nối MJPEG — phải gán sang ảnh
    // khác, xem chú thích ở `BLANK_IMAGE`.
    if (img.getAttribute('src') !== target) img.src = target;
    return () => {
      img.src = BLANK_IMAGE;
    };
  }, [target]);

  return (
    <img
      ref={ref}
      onError={(event) => {
        // Chỉ lùi đúng một lần, tránh nhảy qua nhảy lại khi cả hai đường cùng hỏng.
        if (!fallback && /^https?:\/\//.test(src)) setFallback(true);
        onError?.(event);
      }}
      {...rest}
    />
  );
}

/**
 * Ảnh cảnh báo phóng to.
 *
 * Ảnh trong danh sách chỉ là bản thu nhỏ, nhìn được có chuyện gì đó xảy ra nhưng không
 * đủ để nhận mặt người hay đọc biển số. Bấm vào thì mở bản 1280px ở đây.
 *
 * `onJump` chỉ có ở trang Xem lại, nơi có sẵn đoạn video tương ứng để nhảy tới. Ở màn
 * giám sát trực tiếp thì không truyền, nút sẽ tự ẩn.
 */
export function Lightbox({
  event, onClose, onJump,
}: {
  event: AppEvent; onClose: () => void; onJump?: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-6"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-full w-full max-w-4xl overflow-hidden rounded-xl bg-white
                   shadow-2xl shadow-slate-950/30"
      >
        <div className="card-head !py-2">
          <span className="card-head-title truncate">
            {event.message ?? event.type} · {formatTimestamp(event.ts)}
          </span>
          <button onClick={onClose} className="btn-ghost !px-2 !py-0.5" title="Đóng">
            <X size={12} />
          </button>
        </div>
        {event.snapshot ? (
          <img
            src={api.eventSnapshotUrl(event.id, 1280)}
            alt={event.message ?? 'Ảnh cảnh báo'}
            className="max-h-[70vh] w-full bg-slate-950 object-contain"
          />
        ) : (
          <div className="flex h-64 items-center justify-center text-sm text-slate-400">
            Sự kiện này không có ảnh chụp
          </div>
        )}
        <div className="flex items-center justify-between gap-3 px-3 py-2">
          <span className="truncate text-xs text-slate-500">
            {event.camera_name ?? ''}
          </span>
          {onJump && (
            <button onClick={onJump} className="btn-primary shrink-0">
              <Play size={13} /> Xem đoạn video
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Hộp thoại xác nhận hành động nguy hiểm.
 *
 * Thay cho `window.confirm` — trình duyệt hiện hộp thoại thô, không hợp với phong
 * cách còn lại của ứng dụng và người dùng dễ bấm nhầm. Nút chính (xoá) luôn tô
 * đỏ và có thể hiển thị thêm lời giải thích vì sao cần cân nhắc.
 */
export function ConfirmDialog({
  title, message, confirmLabel = 'Xoá', onConfirm, onCancel, busy = false,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div
      onClick={onCancel}
      className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/70 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm overflow-hidden rounded-xl bg-white shadow-2xl shadow-slate-950/30"
      >
        <div className="flex items-center gap-2 border-b border-slate-200/60 px-4 py-3">
          <AlertTriangle size={16} className="shrink-0 text-rose-600" />
          <span className="text-sm font-semibold text-slate-800">{title}</span>
        </div>
        <p className="px-4 py-3 text-sm leading-relaxed text-slate-600">{message}</p>
        <div className="flex justify-end gap-2 border-t border-slate-200/60 px-4 py-3">
          <button onClick={onCancel} disabled={busy} className="btn-ghost">
            Huỷ
          </button>
          <button onClick={onConfirm} disabled={busy} className="btn-danger">
            {busy ? 'Đang xoá…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
