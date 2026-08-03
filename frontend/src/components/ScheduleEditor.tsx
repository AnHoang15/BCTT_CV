/**
 * Chọn lịch chạy cho pipeline.
 *
 * Tắt công tắc thì AI chạy liên tục 24/7. Bật lên thì chỉ chạy trong các khung giờ đã
 * khai báo; mỗi khung gồm những thứ trong tuần và một khoảng giờ. Nhiều khung ghép
 * được với nhau, ví dụ giờ hành chính các ngày trong tuần cộng thêm buổi sáng thứ Bảy.
 *
 * Ngoài khung giờ, camera vẫn phát hình và vẫn ghi hình — chỉ phần nhận diện tạm nghỉ.
 */
import { Clock, Plus, Trash2 } from 'lucide-react';
import type { ScheduleSlot, ScheduleSpec } from '../types';

/** Số hiệu ngày theo cách gọi của người Việt: 2 là thứ Hai, 8 là Chủ nhật. */
const DAYS: { id: number; label: string }[] = [
  { id: 2, label: 'T2' }, { id: 3, label: 'T3' }, { id: 4, label: 'T4' },
  { id: 5, label: 'T5' }, { id: 6, label: 'T6' }, { id: 7, label: 'T7' },
  { id: 8, label: 'CN' },
];

const WEEKDAYS = [2, 3, 4, 5, 6];

export const DEFAULT_SCHEDULE: ScheduleSpec = {
  enabled: false,
  slots: [{ days: [...WEEKDAYS], from: '08:00', to: '18:00' }],
};

interface Props {
  value: ScheduleSpec;
  onChange: (value: ScheduleSpec) => void;
}

export default function ScheduleEditor({ value, onChange }: Props) {
  const setSlot = (index: number, patch: Partial<ScheduleSlot>) => {
    const slots = value.slots.map((s, i) => (i === index ? { ...s, ...patch } : s));
    onChange({ ...value, slots });
  };

  const toggleDay = (index: number, day: number) => {
    const slot = value.slots[index];
    const days = slot.days.includes(day)
      ? slot.days.filter((d) => d !== day)
      : [...slot.days, day].sort((a, b) => a - b);
    setSlot(index, { days });
  };

  const addSlot = () =>
    onChange({
      ...value,
      slots: [...value.slots, { days: [...WEEKDAYS], from: '08:00', to: '18:00' }],
    });

  const removeSlot = (index: number) =>
    onChange({ ...value, slots: value.slots.filter((_, i) => i !== index) });

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-bold uppercase
                         tracking-wide text-slate-500">
          <Clock size={13} /> Lịch chạy
        </span>
        <button
          role="switch"
          aria-checked={value.enabled}
          aria-label="Bật lịch chạy"
          onClick={() => onChange({ ...value, enabled: !value.enabled })}
          className={`relative h-6 w-11 cursor-pointer rounded-full transition-colors ${
            value.enabled ? 'bg-emerald-600' : 'bg-slate-300'
          }`}
        >
          {/* Núm trượt: track rộng 44px, núm 20px, chừa 2px mỗi bên nên quãng dịch
              đúng bằng 20px. Ghi thẳng khoảng dịch vào `style` cho dễ đối chiếu với
              con số hình học ở trên, thay vì tra ngược lại từ tên lớp Tailwind. */}
          <span
            style={{ transform: `translateX(${value.enabled ? 20 : 0}px)` }}
            className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white
                       shadow-sm transition-transform"
          />
        </button>
      </div>

      {!value.enabled ? (
        <p className="mt-2 text-xs text-slate-500">
          AI chạy liên tục 24/7 — không giới hạn ngày hay giờ.
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {value.slots.map((slot, index) => (
            <div key={index} className="rounded-lg bg-slate-50 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wide text-slate-400">
                  Khung {index + 1}
                </span>
                {value.slots.length > 1 && (
                  <button
                    onClick={() => removeSlot(index)}
                    className="btn !px-1.5 !py-0.5 text-slate-400 hover:bg-rose-50
                               hover:text-rose-600"
                    title="Xoá khung giờ này"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>

              <div className="flex flex-wrap gap-1.5">
                {DAYS.map((day) => {
                  const active = slot.days.includes(day.id);
                  return (
                    <button
                      key={day.id}
                      onClick={() => toggleDay(index, day.id)}
                      className={`h-9 w-9 cursor-pointer rounded-lg border text-xs
                                  font-bold transition-colors ${
                        active
                          ? 'border-emerald-600 bg-emerald-600 text-white'
                          : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300'
                      }`}
                    >
                      {day.label}
                    </button>
                  );
                })}
              </div>

              <div className="mt-2 flex items-center gap-2">
                <input
                  type="time"
                  aria-label={`Giờ bắt đầu khung ${index + 1}`}
                  className="input !py-1.5"
                  value={slot.from}
                  onChange={(event) => setSlot(index, { from: event.target.value })}
                />
                <span className="shrink-0 text-slate-400">→</span>
                <input
                  type="time"
                  aria-label={`Giờ kết thúc khung ${index + 1}`}
                  className="input !py-1.5"
                  value={slot.to}
                  onChange={(event) => setSlot(index, { to: event.target.value })}
                />
              </div>

              {slot.days.length === 0 && (
                <p className="mt-1.5 text-xs font-bold text-rose-600">
                  Chọn ít nhất một ngày trong tuần.
                </p>
              )}
              {slot.from > slot.to && (
                <p className="mt-1.5 text-xs text-amber-700">
                  Khung giờ này vắt qua nửa đêm, hệ thống sẽ chạy sang cả ngày hôm sau.
                </p>
              )}
            </div>
          ))}

          <button
            onClick={addSlot}
            className="flex w-full cursor-pointer items-center justify-center gap-1.5
                       rounded-lg border border-dashed border-slate-300 py-2 text-xs
                       font-bold text-slate-500 hover:border-emerald-400
                       hover:text-emerald-700"
          >
            <Plus size={13} /> Thêm khung giờ khác
          </button>
        </div>
      )}
    </div>
  );
}
