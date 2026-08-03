/**
 * Hộp thoại khai báo camera mới.
 *
 * Đặt ngay ở trang giám sát vì thêm camera là việc người vận hành làm thường xuyên
 * nhất, không đáng phải đi qua một trang quản trị riêng.
 *
 * Nút "Kiểm tra kết nối" gọi thử nguồn video trước khi lưu. Không có bước này thì
 * người dùng chỉ phát hiện đường dẫn sai sau khi camera đã nằm trong danh sách và báo
 * mất tín hiệu.
 */
import { useState } from 'react';
import { Plus, Wifi, X } from 'lucide-react';
import * as api from '../api';
import type { ProbeResult } from '../types';

type Kind = 'usb' | 'rtsp' | 'file';

const PLACEHOLDER: Record<Kind, string> = {
  usb: '0',
  rtsp: 'rtsp://user:pass@192.168.1.10:554/stream',
  file: '/duong/dan/video.mp4',
};

const HELP: Record<Kind, string> = {
  usb: 'Webcam tích hợp thường là 0, webcam cắm ngoài là 1.',
  rtsp: 'Dán nguyên đường dẫn RTSP lấy từ phần mềm của camera.',
  file: 'Đường dẫn tuyệt đối tới tệp video trên máy chạy máy chủ. Video được phát lặp.',
};

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

export default function CameraDialog({ onClose, onCreated }: Props) {
  const [name, setName] = useState('');
  const [kind, setKind] = useState<Kind>('usb');
  const [source, setSource] = useState('');
  const [location, setLocation] = useState('');
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleProbe = async () => {
    if (!source.trim()) return;
    setBusy(true);
    setProbe(null);
    setError(null);
    try {
      setProbe(await api.probeSource(source.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không kiểm tra được nguồn');
    } finally {
      setBusy(false);
    }
  };

  const handleCreate = async () => {
    if (!name.trim() || !source.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createCamera({
        name: name.trim(), source: source.trim(), location: location.trim(), kind,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thêm được camera');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4"
    >
      <div
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-md overflow-hidden rounded-xl bg-white"
      >
        <div className="card-head !py-2.5">
          <span className="card-head-title">Khai báo camera mới</span>
          <button onClick={onClose} className="btn-dark !px-2 !py-0.5">
            <X size={12} />
          </button>
        </div>

        <div className="space-y-3 p-4">
          <div>
            <label className="label" htmlFor="cam-name">Tên camera</label>
            <input
              id="cam-name" className="input" value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Cổng chính"
            />
          </div>

          <div>
            <label className="label" htmlFor="cam-kind">Loại nguồn</label>
            <select
              id="cam-kind" className="input" value={kind}
              onChange={(event) => {
                setKind(event.target.value as Kind);
                setProbe(null);
              }}
            >
              <option value="usb">Webcam cắm trực tiếp</option>
              <option value="rtsp">Camera IP qua mạng</option>
              <option value="file">Tệp video có sẵn</option>
            </select>
          </div>

          <div>
            <label className="label" htmlFor="cam-source">Nguồn</label>
            <input
              id="cam-source"
              className="input font-mono !text-xs"
              value={source}
              onChange={(event) => {
                setSource(event.target.value);
                setProbe(null);
              }}
              placeholder={PLACEHOLDER[kind]}
            />
            <p className="mt-1 text-xs text-slate-400">{HELP[kind]}</p>
          </div>

          <div>
            <label className="label" htmlFor="cam-location">Vị trí lắp đặt</label>
            <input
              id="cam-location" className="input" value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="Tầng 1 — Sảnh"
            />
          </div>

          <button
            onClick={handleProbe}
            disabled={busy || !source.trim()}
            className="btn-ghost w-full"
          >
            <Wifi size={14} /> Kiểm tra kết nối
          </button>

          {probe && (
            <div
              className={`rounded-lg px-3 py-2 text-xs ${
                probe.ok
                  ? 'bg-emerald-50 text-emerald-800'
                  : 'bg-rose-50 text-rose-800'
              }`}
            >
              <p className="font-bold">{probe.message}</p>
              {probe.ok && (
                <p className="mt-0.5">
                  {probe.width}×{probe.height} · {probe.fps} FPS · mở trong{' '}
                  {probe.elapsed_ms} ms
                </p>
              )}
            </div>
          )}

          {error && (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-800">
              {error}
            </p>
          )}

          <div className="flex gap-2 pt-1">
            <button
              onClick={handleCreate}
              disabled={busy || !name.trim() || !source.trim()}
              className="btn-primary flex-1 !py-2.5"
            >
              <Plus size={14} /> Thêm camera
            </button>
            <button onClick={onClose} className="btn-ghost !py-2.5">
              Huỷ
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
