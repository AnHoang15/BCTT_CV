/**
 * Trang xem lại và tìm kiếm.
 *
 * Ô tìm kiếm đặt ngay đầu trang vì đây là cách người vận hành thường bắt đầu. Kết quả
 * trả về dưới dạng **lưới ảnh** chứ không phải danh sách chữ: mỗi ô là ảnh chụp tại
 * đúng thời điểm sự kiện, nhìn là nhận ra ngay có đúng thứ mình tìm hay không. Bấm vào
 * ảnh để xem lớn, bấm nút bên dưới để nhảy tới đúng giây trong video.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Calendar, Clock, Download, Film, Play, Search, Sparkles, Video as VideoIcon, X,
} from 'lucide-react';
import * as api from '../api';
import type { AppEvent, Camera, SearchResult, Segment, TimelineData } from '../types';
import { EmptyState, ErrorBanner, formatTimestamp, Lightbox, todayISO } from './common';

const SECONDS_PER_DAY = 86400;

const EXAMPLES = [
  'người đi vào hôm nay',
  'người đi ra hôm qua buổi chiều',
  'người đi vào từ 8h đến 11h',
];

interface Props {
  cameras: Camera[];
}

export default function Playback({ cameras }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);

  const [cameraId, setCameraId] = useState(cameras[0]?.id ?? '');
  const [date, setDate] = useState(todayISO());
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [activeSegment, setActiveSegment] = useState<Segment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [queryText, setQueryText] = useState('');
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [lightbox, setLightbox] = useState<AppEvent | null>(null);

  useEffect(() => {
    if (!cameraId && cameras.length) setCameraId(cameras[0].id);
  }, [cameras, cameraId]);

  const loadTimeline = useCallback(async () => {
    if (!cameraId) return;
    setLoading(true);
    try {
      const data = await api.getTimeline(cameraId, date);
      setTimeline(data);
      setActiveSegment((current) => {
        const stillValid = current && data.segments.some((s) => s.id === current.id);
        return stillValid ? current : data.segments.find((s) => s.available) ?? null;
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được dữ liệu xem lại');
    } finally {
      setLoading(false);
    }
  }, [cameraId, date]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  /** Nhảy tới thời điểm của một sự kiện: đổi camera/ngày nếu cần rồi tua video. */
  const jumpToEvent = async (event: AppEvent) => {
    if (!event.camera_id) return;
    setLightbox(null);
    if (event.camera_id !== cameraId) setCameraId(event.camera_id);
    const eventDate = event.ts.slice(0, 10);
    if (eventDate !== date) setDate(eventDate);

    try {
      const { segment, seek_seconds } = await api.findSegmentAt(event.camera_id, event.ts);
      setActiveSegment({ ...segment, available: true } as unknown as Segment);
      window.setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.currentTime = seek_seconds;
          videoRef.current.play().catch(() => undefined);
        }
      }, 300);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? `${err.message}. Sự kiện này có thể xảy ra khi chưa bật ghi hình.`
          : 'Không tìm được đoạn video tương ứng',
      );
    }
  };

  const runSearch = async (text?: string) => {
    const q = (text ?? queryText).trim();
    if (!q) return;
    setQueryText(q);
    setSearching(true);
    try {
      // Gửi kèm camera đang chọn ở đầu trang: không có nó thì kết quả trả về sự
      // kiện của mọi camera trong khi ô chọn vẫn ghi tên một camera cụ thể.
      setSearchResult(await api.searchEvents(q, cameraId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tìm kiếm không thành công');
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3">
      <div className="mx-auto max-w-[1500px] space-y-3">
        <header className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-800">
              Xem lại &amp; Tìm kiếm
            </h1>
            <p className="text-xs text-slate-500">
              Phát lại đoạn ghi hình và tra cứu sự kiện bằng câu tiếng Việt
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="input !w-44 !py-1.5"
              value={cameraId}
              onChange={(event) => setCameraId(event.target.value)}
              aria-label="Camera"
            >
              {cameras.map((camera) => (
                <option key={camera.id} value={camera.id}>{camera.name}</option>
              ))}
            </select>
            <input
              type="date"
              className="input !w-36 !py-1.5"
              value={date}
              max={todayISO()}
              onChange={(event) => setDate(event.target.value)}
              aria-label="Ngày"
            />
          </div>
        </header>

        {/* ── Tìm kiếm ─────────────────────────────────────────────── */}
        <section className="card">
          <div className="card-head !py-2">
            <span className="card-head-title flex items-center gap-1.5">
              <Sparkles size={13} /> Tìm kiếm bằng tiếng Việt
            </span>
            {searchResult && (
              <button
                onClick={() => {
                  setSearchResult(null);
                  setQueryText('');
                }}
                className="btn-ghost !px-2 !py-0.5"
              >
                <X size={11} /> Xoá bộ lọc
              </button>
            )}
          </div>

          <div className="p-3">
            <div className="flex gap-2">
              <input
                className="input"
                value={queryText}
                placeholder="vd: người đi vào hôm qua buổi sáng"
                onChange={(event) => setQueryText(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && runSearch()}
              />
              <button
                onClick={() => runSearch()}
                disabled={searching || !queryText.trim()}
                className="btn-primary shrink-0 !px-4"
              >
                <Search size={14} /> Tìm
              </button>
            </div>

            <div className="mt-1.5 flex flex-wrap gap-1">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  onClick={() => runSearch(example)}
                  className="cursor-pointer rounded-full border border-slate-200 px-2
                             py-0.5 text-xs font-medium text-slate-500
                             hover:border-emerald-300 hover:text-emerald-700"
                >
                  {example}
                </button>
              ))}
            </div>

            {searchResult && (
              <>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5
                                rounded-lg border border-emerald-100 bg-emerald-50/70
                                px-2.5 py-1.5 text-xs">
                  <span className="font-bold text-emerald-800">Hệ thống hiểu là:</span>
                  {searchResult.filters.understood.map((item) => (
                    <span key={item} className="text-slate-600">• {item}</span>
                  ))}
                  <span className="ml-auto font-bold text-emerald-700">
                    {searchResult.total} kết quả
                  </span>
                </div>

                {searchResult.results.length === 0 ? (
                  <EmptyState
                    icon={<Search size={28} />}
                    title="Không tìm thấy sự kiện nào"
                    /* Backend giải thích được vì sao rỗng thì hiện đúng lời đó. Câu
                       gợi ý chung chung khiến người dùng đi sửa câu lệnh, trong khi
                       vấn đề thật nằm ở chỗ chưa pipeline nào theo dõi loại đối
                       tượng ấy nên không có gì để tìm. */
                    hint={searchResult.hint
                      ?? 'Thử câu khác, hoặc bỏ bớt điều kiện thời gian.'}
                  />
                ) : (
                  <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3
                                  lg:grid-cols-4 xl:grid-cols-5">
                    {searchResult.results.slice(0, 60).map((event) => (
                      <ResultCard
                        key={event.id}
                        event={event}
                        onOpen={() => setLightbox(event)}
                        onJump={() => jumpToEvent(event)}
                      />
                    ))}
                  </div>
                )}
                {searchResult.results.length > 60 && (
                  <p className="mt-2 text-center text-xs text-slate-400">
                    Đang hiện 60 kết quả đầu trên tổng số {searchResult.total}. Thu hẹp
                    câu hỏi (thêm khung giờ, thêm chiều) để xem đúng cái cần tìm.
                  </p>
                )}
              </>
            )}
          </div>
        </section>

        {/* ── Trình phát, dòng thời gian, sự kiện trong ngày ────────── */}
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_340px]">
          <section className="space-y-3">
            <div className="card">
              <div className="aspect-video bg-slate-950">
                {activeSegment ? (
                  <video
                    ref={videoRef}
                    key={activeSegment.id}
                    src={api.segmentVideoUrl(activeSegment.id)}
                    controls
                    className="h-full w-full"
                    onError={() =>
                      setError(
                        'Trình duyệt không phát được đoạn video này. Nếu OpenCV trên ' +
                        'máy không có bộ mã hoá H.264, hãy chuyển mã tệp bằng ffmpeg.',
                      )
                    }
                  />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-1.5
                                  text-slate-500">
                    <Film size={30} />
                    <p className="text-xs font-bold">
                      {loading ? 'Đang tải…' : 'Không có đoạn ghi hình cho ngày này'}
                    </p>
                  </div>
                )}
              </div>
              {activeSegment && (
                <div className="flex items-center justify-between gap-3 px-3 py-1.5
                                text-xs text-slate-500">
                  <span className="flex items-center gap-1.5">
                    <Clock size={11} /> Bắt đầu {activeSegment.clock}
                  </span>
                  <span className="flex items-center gap-3">
                    <span>{Math.round(activeSegment.duration)} giây</span>
                    {/* Thẻ <a download> chứ không phải fetch: để trình duyệt tự lo
                        việc tải, hiện thanh tiến trình và ghi vào thư mục Downloads.
                        Tải qua JavaScript sẽ phải giữ cả tệp trong bộ nhớ trước.

                        Đoạn đang ghi thì khoá nút lại: tệp MP4 chưa có bảng chỉ mục
                        ở cuối nên tải về cũng không trình phát nào mở được. */}
                    {activeSegment.end_ts ? (
                      <a
                        href={api.segmentDownloadUrl(activeSegment.id)}
                        download
                        className="btn-ghost !px-2 !py-0.5 !text-xs"
                        title="Tải đoạn này về máy, đã vẽ sẵn hộp giới hạn và vạch đếm"
                      >
                        <Download size={12} /> Tải về
                      </a>
                    ) : (
                      <span
                        className="btn-ghost !px-2 !py-0.5 !text-xs opacity-40"
                        title="Đoạn này đang được ghi, chưa tải về được. Chờ hết đoạn
                               hoặc chọn một đoạn cũ hơn."
                      >
                        <Download size={12} /> Đang ghi
                      </span>
                    )}
                  </span>
                </div>
              )}
            </div>

            <div className="card">
              <div className="card-head !py-2">
                <span className="card-head-title flex items-center gap-1.5">
                  <Calendar size={12} /> Dòng thời gian
                </span>
                <span className="text-xs text-slate-400">
                  {timeline?.segments.length ?? 0} đoạn · {timeline?.events.length ?? 0} sự kiện
                </span>
              </div>
              <div className="p-3">
                <Timeline
                  timeline={timeline}
                  activeSegmentId={activeSegment?.id ?? null}
                  onPickSegment={setActiveSegment}
                  onPickEvent={jumpToEvent}
                />
                {!!timeline?.segments.length && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {timeline.segments.map((segment) => (
                      <button
                        key={segment.id}
                        disabled={!segment.available}
                        onClick={() => setActiveSegment(segment)}
                        className={`cursor-pointer rounded border px-1.5 py-0.5
                                    text-xs font-semibold transition-colors
                                    disabled:cursor-not-allowed disabled:opacity-40 ${
                          activeSegment?.id === segment.id
                            ? 'border-emerald-500 bg-emerald-50 text-emerald-700'
                            : 'border-slate-200 text-slate-500 hover:border-slate-300'
                        }`}
                      >
                        {segment.clock}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>

          <aside className="card flex max-h-[560px] flex-col">
            <div className="card-head !py-2">
              <span className="card-head-title">Sự kiện ngày {date}</span>
              <span className="text-xs text-slate-400">
                {timeline?.events.length ?? 0}
              </span>
            </div>
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-2">
              {!timeline?.events.length ? (
                <EmptyState
                  icon={<VideoIcon size={28} />}
                  title="Chưa có sự kiện"
                  hint="Bật một pipeline đếm để hệ thống ghi nhận."
                />
              ) : (
                <div className="grid grid-cols-3 gap-1.5">
                  {timeline.events.map((event) => (
                    <ResultCard
                      key={event.id}
                      event={event}
                      compact
                      onOpen={() => setLightbox(event)}
                      onJump={() => jumpToEvent(event)}
                    />
                  ))}
                </div>
              )}
            </div>
          </aside>
        </div>

        {error && <ErrorBanner message={error} onRetry={() => setError(null)} />}
      </div>

      {lightbox && (
        <Lightbox
          event={lightbox}
          onClose={() => setLightbox(null)}
          onJump={() => jumpToEvent(lightbox)}
        />
      )}
    </div>
  );
}

/* ── Một ô ảnh kết quả ────────────────────────────────────────────────── */
function ResultCard({
  event, compact, onOpen, onJump,
}: {
  event: AppEvent; compact?: boolean; onOpen: () => void; onJump: () => void;
}) {
  const isIn = event.direction === 'in';
  return (
    <div className="group relative overflow-hidden rounded-lg border border-slate-200
                    bg-slate-900">
      <button onClick={onOpen} className="block w-full cursor-zoom-in">
        {event.snapshot ? (
          <img
            src={api.eventSnapshotUrl(event.id, compact ? 200 : 400)}
            alt={event.message ?? ''}
            loading="lazy"
            className="aspect-video w-full object-cover transition-transform
                       group-hover:scale-105"
          />
        ) : (
          <div className="flex aspect-video w-full items-center justify-center bg-slate-100">
            <VideoIcon size={18} className="text-slate-300" />
          </div>
        )}
      </button>

      <span
        className={`pointer-events-none absolute left-1 top-1 rounded px-1 py-0.5
                    text-[10px] font-bold text-white ${
          isIn ? 'bg-emerald-600' : 'bg-rose-600'
        }`}
      >
        {isIn ? 'VÀO' : 'RA'}
      </span>

      <div className="bg-white px-1.5 py-1">
        <p className="truncate text-xs font-semibold text-slate-700">
          {event.clock ?? formatTimestamp(event.ts).split(' ')[1]}
        </p>
        {!compact && (
          <p className="truncate text-[10px] text-slate-400">{event.camera_name ?? ''}</p>
        )}
      </div>

      <button
        onClick={onJump}
        title="Nhảy tới đoạn video"
        className="absolute bottom-8 right-1 cursor-pointer rounded-full bg-slate-900/80
                   p-1.5 text-white opacity-0 transition-opacity hover:bg-emerald-600
                   group-hover:opacity-100"
      >
        <Play size={11} />
      </button>
    </div>
  );
}

/* ── Xem ảnh lớn ──────────────────────────────────────────────────────── */
/* ── Thanh thời gian 24 giờ ───────────────────────────────────────────── */
function Timeline({
  timeline, activeSegmentId, onPickSegment, onPickEvent,
}: {
  timeline: TimelineData | null;
  activeSegmentId: string | null;
  onPickSegment: (segment: Segment) => void;
  onPickEvent: (event: AppEvent) => void;
}) {
  const hourMarks = useMemo(() => Array.from({ length: 25 }, (_, i) => i), []);

  return (
    <div>
      <div className="relative h-10 overflow-hidden rounded-lg bg-slate-100">
        {hourMarks.map((hour) => (
          <div
            key={hour}
            className="absolute top-0 h-full border-l border-slate-200"
            style={{ left: `${(hour / 24) * 100}%` }}
          />
        ))}

        {timeline?.segments.map((segment) => {
          const left = (segment.offset_seconds / SECONDS_PER_DAY) * 100;
          const width = Math.max(0.15, ((segment.duration || 60) / SECONDS_PER_DAY) * 100);
          return (
            <button
              key={segment.id}
              onClick={() => segment.available && onPickSegment(segment)}
              title={`Đoạn ${segment.clock}`}
              className={`absolute top-1 h-5 cursor-pointer rounded-sm transition-colors ${
                activeSegmentId === segment.id
                  ? 'bg-emerald-600'
                  : segment.available
                    ? 'bg-emerald-300 hover:bg-emerald-400'
                    : 'bg-slate-300'
              }`}
              style={{ left: `${left}%`, width: `${width}%` }}
            />
          );
        })}

        {timeline?.events.map((event) => (
          <button
            key={event.id}
            onClick={() => onPickEvent(event)}
            title={`${event.clock} — ${event.message ?? ''}`}
            className={`absolute bottom-1 h-3 w-1 cursor-pointer rounded-full
                        transition-transform hover:scale-y-150 ${
              event.direction === 'in' ? 'bg-emerald-600' : 'bg-rose-500'
            }`}
            style={{ left: `${((event.offset_seconds ?? 0) / SECONDS_PER_DAY) * 100}%` }}
          />
        ))}
      </div>

      <div className="mt-0.5 flex justify-between text-[10px] text-slate-400">
        {[0, 4, 8, 12, 16, 20, 24].map((hour) => (
          <span key={hour}>{String(hour).padStart(2, '0')}h</span>
        ))}
      </div>
    </div>
  );
}
