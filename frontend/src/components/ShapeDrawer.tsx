/**
 * Công cụ vẽ vạch và vùng trên ảnh chụp từ camera.
 *
 * Hai chế độ:
 *   - **Vạch**: kéo chuột để vẽ một đoạn thẳng bất kỳ, kéo hai đầu để chỉnh. Vạch chéo
 *     hoàn toàn hợp lệ, không bắt buộc phải ngang hay dọc.
 *   - **Vùng**: bấm lần lượt để thêm đỉnh, kéo đỉnh để chỉnh, bấm lại vào đỉnh đầu tiên
 *     để khép kín.
 *
 * Toạ độ lưu ở dạng chuẩn hoá 0..1 chứ không phải điểm ảnh, nhờ vậy hình vẽ vẫn đúng vị
 * trí khi camera đổi độ phân giải, và dùng chung được cho ảnh hiển thị đã thu nhỏ lẫn
 * khung hình gốc mà bộ đếm làm việc.
 */
import { useEffect, useRef, useState } from 'react';
import {
  Eraser, MoveHorizontal, MoveVertical, RefreshCw, Repeat, Square, Undo2,
} from 'lucide-react';
import * as api from '../api';
import type { LineSpec, ZonePoint } from '../types';

/** Bấm trong bán kính này (theo toạ độ chuẩn hoá) coi như bấm trúng đỉnh. */
const HIT_RADIUS = 0.035;
/** Chuột phải đi xa hơn ngần này mới coi là đang kéo, không phải bấm hụt. */
const MIN_DRAG = 0.015;

interface Props {
  cameraId: string;
  shape: 'line' | 'polygon';
  /** `null` nghĩa là chưa vẽ gì — khung hiện lời nhắc thay vì một vạch dựng sẵn. */
  line: LineSpec | null;
  zone: ZonePoint[];
  flip: boolean;
  onLineChange: (line: LineSpec) => void;
  onZoneChange: (zone: ZonePoint[]) => void;
  onFlipChange: (flip: boolean) => void;
  /** Đổi kiểu hình vẽ. Kéo theo bài toán: vạch → đếm ra/vào, vùng → đếm trong vùng. */
  onShapeChange: (shape: 'line' | 'polygon') => void;
  /** Chỉ hiển thị hình đã vẽ, không cho sửa. Dùng ở bước kiểm tra lại cấu hình. */
  readOnly?: boolean;
}

export default function ShapeDrawer({
  cameraId, shape, line, zone, flip,
  onLineChange, onZoneChange, onFlipChange, onShapeChange, readOnly = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [nonce, setNonce] = useState(() => Date.now());
  const [dragging, setDragging] = useState<
    { kind: 'line-start' | 'line-end' | 'line-new' } | { kind: 'vertex'; index: number } | null
  >(null);
  const [imageError, setImageError] = useState(false);
  // Điểm bắt đầu của thao tác vẽ vạch mới, giữ lại cho tới khi chuột thật sự di
  // chuyển. Chưa di chuyển thì chưa đụng tới vạch cũ.
  const pendingStart = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    setImageError(false);
  }, [cameraId, nonce]);

  const toNormalized = (clientX: number, clientY: number) => {
    const rect = containerRef.current!.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (clientY - rect.top) / rect.height)),
    };
  };

  const handlePointerDown = (event: React.PointerEvent) => {
    if (readOnly) return;
    const point = toNormalized(event.clientX, event.clientY);
    (event.target as Element).setPointerCapture(event.pointerId);

    if (shape === 'line') {
      const near = (x: number, y: number) => Math.hypot(point.x - x, point.y - y) < HIT_RADIUS;
      if (line && near(line.x1, line.y1)) setDragging({ kind: 'line-start' });
      else if (line && near(line.x2, line.y2)) setDragging({ kind: 'line-end' });
      else {
        // Bấm chỗ trống: ghi nhớ điểm bắt đầu nhưng CHƯA sửa vạch. Nếu người dùng chỉ
        // bấm rồi thả mà không kéo, vạch cũ phải còn nguyên — bản trước ghi đè ngay ở
        // đây nên một cú bấm là vạch co về một điểm và biến mất.
        pendingStart.current = point;
        setDragging({ kind: 'line-new' });
      }
      return;
    }

    // Chế độ vùng: bấm trúng đỉnh thì kéo đỉnh đó, bấm chỗ trống thì thêm đỉnh mới.
    const hitIndex = zone.findIndex(
      (p) => Math.hypot(point.x - p.x, point.y - p.y) < HIT_RADIUS,
    );
    if (hitIndex >= 0) {
      setDragging({ kind: 'vertex', index: hitIndex });
    } else {
      onZoneChange([...zone, point]);
      setDragging({ kind: 'vertex', index: zone.length });
    }
  };

  const handlePointerMove = (event: React.PointerEvent) => {
    if (!dragging) return;
    const point = toNormalized(event.clientX, event.clientY);

    if (dragging.kind === 'vertex') {
      const next = zone.slice();
      next[dragging.index] = point;
      onZoneChange(next);
      return;
    }
    if (dragging.kind === 'line-start' && line) {
      onLineChange({ ...line, x1: point.x, y1: point.y });
      return;
    }

    // Vẽ vạch mới: chỉ bắt đầu khi chuột đã đi đủ xa điểm bấm, tránh biến một cú bấm
    // hụt thành vạch dài bằng không.
    const start = pendingStart.current;
    if (start) {
      if (Math.hypot(point.x - start.x, point.y - start.y) < MIN_DRAG) return;
      pendingStart.current = null;
      onLineChange({ x1: start.x, y1: start.y, x2: point.x, y2: point.y });
      return;
    }
    if (line) onLineChange({ ...line, x2: point.x, y2: point.y });
  };

  const handlePointerUp = () => {
    pendingStart.current = null;
    setDragging(null);
  };

  // Pháp tuyến của vạch, dùng vẽ mũi tên chỉ chiều Vào/Ra giống hệt backend.
  const dx = line ? line.x2 - line.x1 : 0;
  const dy = line ? line.y2 - line.y1 : 0;
  const length = Math.hypot(dx, dy) || 1;
  const sign = flip ? -1 : 1;
  const midX = line ? (line.x1 + line.x2) / 2 : 0.5;
  const midY = line ? (line.y1 + line.y2) / 2 : 0.5;
  const normalX = (-dy / length) * 0.12 * sign;
  const normalY = (dx / length) * 0.12 * sign;

  const polygonPoints = zone.map((p) => `${p.x},${p.y}`).join(' ');
  const enoughVertices = zone.length >= 3;

  return (
    <div className="space-y-2">
      {/* Chọn kiểu hình. Đặt ngay trên khung vẽ để người dùng luôn thấy có hai lựa
          chọn, thay vì phải quay lại bước trước mới đổi được. */}
      <div className={`inline-flex rounded-lg border border-slate-200 bg-white p-1 ${
        readOnly ? 'hidden' : ''
      }`}>
        {([
          { id: 'line' as const, label: 'Vẽ vạch', desc: 'đếm lượt đi qua' },
          { id: 'polygon' as const, label: 'Vẽ vùng', desc: 'đếm trong khu vực' },
        ]).map((option) => (
          <button
            key={option.id}
            onClick={() => onShapeChange(option.id)}
            className={`cursor-pointer rounded-md px-3.5 py-1.5 text-sm font-bold
                        transition-colors ${
              shape === option.id
                ? 'bg-emerald-600 text-white'
                : 'text-slate-500 hover:bg-slate-50'
            }`}
          >
            {option.label}
            <span
              className={`ml-1.5 font-medium ${
                shape === option.id ? 'text-emerald-100' : 'text-slate-400'
              }`}
            >
              — {option.desc}
            </span>
          </button>
        ))}
      </div>

      <div
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        className={`relative aspect-video w-full select-none touch-none overflow-hidden
                    rounded-xl border border-slate-300 bg-slate-950 ${
          readOnly ? '' : 'cursor-crosshair'
        }`}
      >
        {imageError ? (
          <div className="flex h-full flex-col items-center justify-center gap-2
                          text-xs text-slate-400">
            <p>Không lấy được ảnh từ camera</p>
            <button onClick={() => setNonce(Date.now())} className="btn-ghost !py-1">
              <RefreshCw size={12} /> Thử lại
            </button>
          </div>
        ) : (
          <img
            src={api.snapshotUrl(cameraId, nonce, true)}
            alt="Khung hình camera"
            onError={() => setImageError(true)}
            className="pointer-events-none h-full w-full object-contain"
            draggable={false}
          />
        )}

        <svg
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          className="pointer-events-none absolute inset-0 h-full w-full"
        >
          <defs>
            <marker id="arrow-in" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#10b981" />
            </marker>
            <marker id="arrow-out" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#f43f5e" />
            </marker>
          </defs>

          {shape === 'line' ? (
            line && (
            <>
              <line
                x1={line.x1} y1={line.y1} x2={line.x2} y2={line.y2}
                stroke="#facc15" vectorEffect="non-scaling-stroke" style={{ strokeWidth: 3 }}
              />
              <line
                x1={midX} y1={midY} x2={midX + normalX} y2={midY + normalY}
                stroke="#10b981" markerEnd="url(#arrow-in)"
                vectorEffect="non-scaling-stroke" style={{ strokeWidth: 2.5 }}
              />
              <line
                x1={midX} y1={midY} x2={midX - normalX} y2={midY - normalY}
                stroke="#f43f5e" markerEnd="url(#arrow-out)"
                vectorEffect="non-scaling-stroke" style={{ strokeWidth: 2.5 }}
              />
              <circle cx={line.x1} cy={line.y1} r={0.013} fill="#facc15" />
              <circle cx={line.x2} cy={line.y2} r={0.013} fill="#facc15" />
            </>
            )
          ) : (
            <>
              {enoughVertices && (
                <polygon
                  points={polygonPoints}
                  fill="#22d3ee" fillOpacity={0.18}
                  stroke="#facc15" vectorEffect="non-scaling-stroke"
                  style={{ strokeWidth: 3 }}
                />
              )}
              {!enoughVertices && zone.length > 1 && (
                <polyline
                  points={polygonPoints}
                  fill="none" stroke="#facc15"
                  vectorEffect="non-scaling-stroke" style={{ strokeWidth: 3 }}
                />
              )}
              {zone.map((point, index) => (
                <circle
                  key={index}
                  cx={point.x} cy={point.y} r={0.013}
                  fill={index === 0 ? '#10b981' : '#facc15'}
                />
              ))}
            </>
          )}
        </svg>

        {shape === 'line' && line && (
          <>
            <span
              className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2
                         rounded bg-emerald-500 px-1.5 py-0.5 text-xs font-bold text-white"
              style={{
                left: `${(midX + normalX * 1.35) * 100}%`,
                top: `${(midY + normalY * 1.35) * 100}%`,
              }}
            >
              VÀO
            </span>
            <span
              className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2
                         rounded bg-rose-500 px-1.5 py-0.5 text-xs font-bold text-white"
              style={{
                left: `${(midX - normalX * 1.35) * 100}%`,
                top: `${(midY - normalY * 1.35) * 100}%`,
              }}
            >
              RA
            </span>
          </>
        )}

        {!readOnly && ((shape === 'line' && !line) || (shape === 'polygon' && zone.length === 0)) && (
          <span className="pointer-events-none absolute inset-0 flex items-center
                           justify-center bg-slate-950/45 text-center text-sm
                           font-bold text-white">
            {shape === 'line'
              ? 'Kéo chuột trên ảnh để vẽ vạch đếm'
              : 'Bấm lần lượt trên ảnh để thêm đỉnh của vùng'}
          </span>
        )}

        {shape === 'polygon' && zone.length > 0 && (
          <span className="pointer-events-none absolute left-2 top-2 chip-dark">
            {zone.length} đỉnh{!enoughVertices && ' — cần ít nhất 3'}
          </span>
        )}
      </div>

      <div className={`flex-wrap items-center gap-1.5 ${readOnly ? 'hidden' : 'flex'}`}>
        {shape === 'line' ? (
          <>
            <button
              onClick={() => onLineChange({ x1: 0, y1: 0.55, x2: 1, y2: 0.55 })}
              className="btn-ghost !py-1"
            >
              <MoveHorizontal size={13} /> Ngang
            </button>
            <button
              onClick={() => onLineChange({ x1: 0.5, y1: 0, x2: 0.5, y2: 1 })}
              className="btn-ghost !py-1"
            >
              <MoveVertical size={13} /> Dọc
            </button>
            <button onClick={() => onFlipChange(!flip)} className="btn-ghost !py-1">
              <Repeat size={13} /> Đảo Vào/Ra
            </button>
          </>
        ) : (
          <>
            <button
              onClick={() => onZoneChange(zone.slice(0, -1))}
              disabled={zone.length === 0}
              className="btn-ghost !py-1"
            >
              <Undo2 size={13} /> Bỏ đỉnh cuối
            </button>
            <button onClick={() => onZoneChange([])} className="btn-ghost !py-1">
              <Eraser size={13} /> Xoá hết
            </button>
            <button
              onClick={() =>
                onZoneChange([
                  { x: 0.25, y: 0.3 }, { x: 0.75, y: 0.3 },
                  { x: 0.75, y: 0.8 }, { x: 0.25, y: 0.8 },
                ])
              }
              className="btn-ghost !py-1"
            >
              <Square size={13} /> Vùng chữ nhật
            </button>
          </>
        )}
        <button onClick={() => setNonce(Date.now())} className="btn-ghost !py-1">
          <RefreshCw size={13} /> Ảnh mới
        </button>
      </div>

      <p className={`rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600 ${readOnly ? 'hidden' : ''}`}>
        {shape === 'line' ? (
          <>
            Kéo chuột trên ảnh để vẽ vạch theo hướng bất kỳ, kể cả vạch chéo. Kéo hai
            chấm vàng để chỉnh lại hai đầu. Đặt vạch đúng chỗ bàn chân đi qua, thường
            thấp hơn giữa khung hình. Người đi cắt ngang vạch được đếm chính xác nhất.
          </>
        ) : (
          <>
            Bấm lần lượt trên ảnh để thêm từng đỉnh của vùng, kéo chấm vàng để chỉnh.
            Đỉnh đầu tiên có màu xanh. Hệ thống tính một đối tượng là ở trong vùng khi
            <b> bàn chân</b> của đối tượng đó nằm trong đa giác.
          </>
        )}
      </p>
    </div>
  );
}
