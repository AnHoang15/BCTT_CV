import { useCallback, useEffect, useState } from 'react';
import { Camera as CameraIcon, Eye, Search, User } from 'lucide-react';
import * as api from './api';
import type { Camera, Summary } from './types';
import LiveMonitor from './components/LiveMonitor';
import PipelineBuilder from './components/PipelineBuilder';
import Playback from './components/Playback';
import { ErrorBanner, SkeletonGrid } from './components/common';

type Page = 'monitor' | 'builder' | 'playback';

const NAV: { id: Page; label: string; icon: JSX.Element }[] = [
  { id: 'monitor', label: 'Giám sát', icon: <Eye size={18} /> },
  { id: 'builder', label: 'Cấu hình', icon: <CameraIcon size={18} /> },
  { id: 'playback', label: 'Xem lại', icon: <Search size={18} /> },
];

export default function App() {
  const [page, setPage] = useState<Page>('monitor');
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [cameraList, summaryData] = await Promise.all([
        api.listCameras(),
        api.getSummary(),
      ]);
      setCameras(cameraList);
      setSummary(summaryData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không kết nối được backend');
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  // Trang giám sát và xem lại trải hết chiều ngang, các trang còn lại có lề.
  const edgeToEdge = page === 'monitor' || page === 'playback';

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      {/* ── Thanh trên cùng ───────────────────────────────────────────────
          Nền trắng, chỉ ngăn cách với nội dung bằng một đường viền mảnh. Toàn bộ
          màu nhấn dồn cho tab đang chọn và nút thao tác. */}
      <header className="z-20 flex h-[4.5rem] shrink-0 items-center justify-between
                         border-b border-slate-200 bg-white px-5">
        <div className="flex flex-1 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl
                          bg-emerald-600 text-white shadow-sm shadow-emerald-600/30">
            <Eye size={22} />
          </div>
          <div className="hidden sm:block">
            <h1 className="text-xl font-bold leading-tight tracking-tight text-slate-800">
              VisionOS
            </h1>
            <p className="text-xs leading-tight text-slate-400">
              Giám sát camera thông minh
            </p>
          </div>
        </div>

        <nav className="flex h-full items-center justify-center gap-1">
          {NAV.map((item) => (
            <button
              key={item.id}
              onClick={() => setPage(item.id)}
              title={item.label}
                          className={`flex h-full cursor-pointer items-center gap-2 border-b-[3px]
                          px-5 text-sm font-semibold transition-all ${
                page === item.id
                  ? 'border-emerald-600 bg-emerald-50/60 text-emerald-700'
                  : 'border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-800'
              }`}
            >
              <span className="shrink-0">{item.icon}</span>
              <span className="hidden md:inline">{item.label}</span>
              {item.id === 'monitor' && !!summary?.unread_events && (
                <span className="ml-1 rounded-full bg-rose-600 px-1.5 py-0.5
                                 text-xs font-semibold text-white">
                  {summary.unread_events}
                </span>
              )}
            </button>
          ))}
        </nav>

        <div className="flex flex-1 items-center justify-end gap-3">
          <div className="flex items-center gap-2 rounded-lg border border-slate-200
                          bg-slate-50 px-2.5 py-1.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-full
                            bg-slate-200 text-slate-600">
              <User size={15} />
            </div>
            <span className="hidden text-sm font-semibold text-slate-700 sm:inline">admin</span>
          </div>
        </div>
      </header>

      {/* ── Nội dung ──────────────────────────────────────────────────── */}
      <div className="flex min-h-0 flex-1 flex-col bg-neutral-50 text-neutral-800">
        <main
          className={`flex min-h-0 flex-1 flex-col ${
            edgeToEdge ? 'overflow-hidden p-0' : 'overflow-y-auto p-4 lg:p-6'
          }`}
        >
          {error && (
            <div className="m-4">
              {/* Không nối thêm gợi ý ở đây: `api.ts` đã nói rõ backend chưa chạy hay
                  không phản hồi, nối nữa thành hai câu trùng ý trong cùng một dòng. */}
              <ErrorBanner message={error} onRetry={refresh} />
            </div>
          )}

          {!ready && (
            <div className="p-4 lg:p-6">
              <SkeletonGrid count={4} />
            </div>
          )}

          {ready && page === 'monitor' && (
            <LiveMonitor cameras={cameras} onChanged={refresh} />
          )}
          {ready && page === 'builder' && (
            <PipelineBuilder cameras={cameras} onChanged={refresh} />
          )}
          {ready && page === 'playback' && <Playback cameras={cameras} />}
        </main>
      </div>
    </div>
  );
}
