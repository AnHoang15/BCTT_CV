/**
 * Trang cấu hình pipeline.
 *
 * Hai chế độ hiển thị tách bạch: mặc định là danh sách pipeline đã tạo, bấm "Tạo
 * pipeline mới" thì chuyển sang trình hướng dẫn chiếm toàn bộ chiều ngang. Trong lúc
 * đang tạo, danh sách được ẩn đi để không phân tán chú ý.
 *
 * Trình hướng dẫn gồm bốn bước:
 *   1. Chọn camera
 *   2. Chọn bài toán
 *   3. Chọn luồng xử lý, đối tượng và vẽ hình — cùng một màn, vì người dùng thường
 *      nhìn khung hình rồi mới quyết định đếm theo vạch hay theo vùng
 *   4. Kiểm tra và chạy
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, Camera as CameraIcon, Check, ChevronLeft, ChevronRight,
  Cpu, Pencil, Play, Plus, Sparkles, Square, Trash2, Wand2, X,
} from 'lucide-react';
import * as api from '../api';
import type {
  AutoReset, Camera, CountDirection, LineSpec, Pipeline, PipelineMode, PromptPreview,
  ScheduleSpec, TaskCatalog, TaskType, ZonePoint,
} from '../types';
import ScheduleEditor, { DEFAULT_SCHEDULE } from './ScheduleEditor';
import ShapeDrawer from './ShapeDrawer';
import { EmptyState, ErrorBanner, SkeletonCard, StatusDot, StreamImage, useToast } from './common';

/** Khung bọc một nhóm tham số, để bước cấu hình không thành một dải trôi liền mạch. */
function ParamBox({
  title, hint, children,
}: {
  title?: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-3">
      {title && (
        <div className="mb-2">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
            {title}
          </h3>
          {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
        </div>
      )}
      {children}
    </section>
  );
}

// Không có hình mặc định: người dùng phải tự vẽ. Một vạch dựng sẵn giữa khung dễ bị
// bấm "Tiếp tục" luôn mà không để ý, dẫn tới pipeline đếm sai chỗ.
// Bốn bước: việc chọn luồng và vẽ hình gộp chung vì hai thứ này người dùng thường
// cân nhắc cùng lúc — nhìn khung hình rồi mới quyết định đếm kiểu gì.
const STEPS = ['Camera', 'Bài toán', 'Luồng & hình vẽ', 'Kiểm tra'];

/**
 * Ngưỡng tin cậy mặc định, phải khớp `YOLO_CONF` trong `backend/app/config.py`.
 *
 * Lệch nhau thì pipeline tạo qua giao diện chạy một ngưỡng, pipeline tạo qua API chạy
 * ngưỡng khác, mà không có gì báo. Trước đây giá trị này bị chép cứng ở hai chỗ trong
 * tệp, nên đổi một chỗ là lệch ngay.
 */
const NGUONG_TIN_CAY_MAC_DINH = 0.25;

interface Props {
  cameras: Camera[];
  onChanged: () => void;
}

export default function PipelineBuilder({ cameras, onChanged }: Props) {
  const { toast } = useToast();
  const [catalog, setCatalog] = useState<TaskCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [creating, setCreating] = useState(false);
  const [step, setStep] = useState(0);
  /* Chọn được nhiều camera: mỗi camera sinh ra một pipeline riêng, cùng tham số
     nhưng số đếm tách bạch. Hình vẽ thì bắt buộc phải riêng — vạch đặt trên khung
     hình camera này không có nghĩa gì trên camera khác. */
  const [cameraIds, setCameraIds] = useState<string[]>([]);
  /** Camera đang được vẽ ở bước 3. */
  const [drawingFor, setDrawingFor] = useState('');
  const [task, setTask] = useState<TaskType>('counting');
  const [mode, setMode] = useState<PipelineMode>('standard');
  const [prompt, setPrompt] = useState('');
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [classes, setClasses] = useState<string[]>(['person']);
  /* Hình vẽ lưu theo mã camera. Chọn ba camera thì có ba vạch, không dùng chung. */
  const [lines, setLines] = useState<Record<string, LineSpec | null>>({});
  const [zones, setZones] = useState<Record<string, ZonePoint[]>>({});
  // Kiểu hình vẽ tách riêng khỏi bài toán: người dùng chọn "Đếm đối tượng" ở bước 2,
  // rồi kiểu hình ở bước 3 mới quyết định là đếm qua vạch hay đếm trong vùng.
  const [shape, _setShape] = useState<'line' | 'polygon'>('line');
  /** Đổi kiểu hình và xoá dữ liệu hình kia để không gửi lên backend shape thừa. */
  const setShape = (next: 'line' | 'polygon') => {
    if (next !== shape) {
      if (next === 'polygon') setLines({});
      else setZones({});
    }
    _setShape(next);
  };
  const [flip, setFlip] = useState(false);
  const [name, setName] = useState('');
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null);
  /** Đang sửa pipeline nào; null nghĩa là đang tạo mới. */
  const [editingId, setEditingId] = useState<string | null>(null);

  // Tham số vận hành
  const [direction, setDirection] = useState<CountDirection>('both');
  const [maxCount, setMaxCount] = useState('');
  const [autoReset, setAutoReset] = useState<AutoReset>('never');
  const [targetFps, setTargetFps] = useState(15);
  // Phải khớp YOLO_CONF trong backend/app/config.py.
  // Ghi chú cũ ở đây nói 0,35 tốt hơn 0,25 — kết luận đó ĐÃ BỊ RÚT LẠI: phép đo sinh ra
  // nó chạy qua đường rút gọn, thiếu bước khử hộp trùng và bước loại hộp quá nhỏ. Chạy
  // qua đúng đường xử lý thật thì hai giá trị cho kết quả bằng nhau.
  const [conf, setConf] = useState(NGUONG_TIN_CAY_MAC_DINH);
  const [schedule, setSchedule] = useState<ScheduleSpec>(DEFAULT_SCHEDULE);

  const load = useCallback(async () => {
    try {
      const list = await api.listPipelines();
      setPipelines(list);
      const running = list.find((p) => p.running) ?? list[0];
      if (running) setSelectedPipeline((current) => current ?? running.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách pipeline');
    }
  }, []);

  const loadCatalog = useCallback(() => {
    api.getTaskCatalog()
      .then((data) => {
        setCatalog(data);
        setCatalogError(null);
      })
      .catch((err) => {
        setCatalog(null);
        setCatalogError(err instanceof Error ? err.message : 'Không tải được danh mục');
      });
  }, []);

  useEffect(() => {
    loadCatalog();
    load();
    const timer = window.setInterval(load, 4000);
    return () => window.clearInterval(timer);
  }, [load, loadCatalog]);

  // Hỏi backend xem nó hiểu câu lệnh ra sao, sau khi người dùng ngừng gõ.
  useEffect(() => {
    if (mode !== 'smart' || !prompt.trim()) {
      setPreview(null);
      return;
    }
    const timer = window.setTimeout(() => {
      api.previewPrompt(prompt.trim()).then(setPreview).catch(() => setPreview(null));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [prompt, mode]);

  // Luồng Thông minh không có ô chọn đối tượng; giữ sẵn lớp "người" để backend
  // không từ chối vì thiếu lớp.
  useEffect(() => {
    if (mode === 'smart') setClasses((current) => (current.length ? current : ['person']));
  }, [mode]);

  /** Các camera đã chọn, theo đúng thứ tự hiển thị trong danh sách. */
  const selectedCameras = useMemo(
    () => cameras.filter((c) => cameraIds.includes(c.id)),
    [cameras, cameraIds],
  );
  /** Camera đang vẽ; rơi về cái đầu tiên nếu lựa chọn cũ đã bị bỏ tick. */
  const drawingCamera = useMemo(
    () => selectedCameras.find((c) => c.id === drawingFor) ?? selectedCameras[0] ?? null,
    [selectedCameras, drawingFor],
  );

  const taskDef = catalog?.tasks.find((t) => t.id === task);
  const needsShape = Boolean(taskDef?.needs_shape);
  const maxStep = 3;

  /** Bài toán thật gửi xuống backend: vạch thì đếm qua vạch, vùng thì đếm trong vùng. */
  const effectiveTask: TaskType =
    task === 'detection' ? 'detection' : shape === 'polygon' ? 'zone' : 'counting';

  /** Camera nào chưa vẽ xong hình. Mỗi camera phải có hình của riêng nó. */
  const missingShape = useMemo(() => {
    if (!needsShape) return [];
    return selectedCameras.filter((camera) => (
      shape === 'line'
        ? !lines[camera.id]
        : (zones[camera.id]?.length ?? 0) < 3
    ));
  }, [needsShape, selectedCameras, shape, lines, zones]);

  const canAdvance = useMemo(() => {
    if (step === 0) return cameraIds.length > 0;
    if (step === 2) {
      if (classes.length === 0) return false;
      if (mode === 'smart' && !prompt.trim()) return false;
      return missingShape.length === 0;
    }
    return true;
  }, [step, cameraIds, classes, mode, prompt, missingShape]);

  const resetWizard = () => {
    setStep(0);
    setEditingId(null);
    setCameraIds([]);
    setDrawingFor('');
    setTask('counting');
    setMode('standard');
    setPrompt('');
    setPreview(null);
    setClasses(['person']);
    setLines({});
    setZones({});
    setShape('line');
    setFlip(false);
    setName('');
    setDirection('both');
    setMaxCount('');
    setAutoReset('never');
    setTargetFps(15);
    setConf(NGUONG_TIN_CAY_MAC_DINH);
    setSchedule(DEFAULT_SCHEDULE);
  };

  const exitWizard = () => {
    setCreating(false);
    resetWizard();
  };

  /**
   * Mở trình hướng dẫn với dữ liệu của một pipeline có sẵn.
   *
   * Bắt đầu ở bước 2 vì camera không đổi được: pipeline gắn chặt với camera nó đang
   * theo dõi, muốn đổi thì tạo cái mới. Các bước còn lại sửa thoải mái, kể cả vạch và
   * vùng — backend tự nạp lại cấu hình cho pipeline đang chạy.
   */
  const startEdit = (pipeline: Pipeline) => {
    setEditingId(pipeline.id);
    // Sửa thì chỉ một camera: pipeline gắn chặt với camera nó đang theo dõi.
    setCameraIds([pipeline.camera_id]);
    setDrawingFor(pipeline.camera_id);
    // Giao diện gộp hai bài toán đếm làm một, kiểu hình vẽ mới là thứ phân biệt.
    setTask(pipeline.task === 'detection' ? 'detection' : 'counting');
    setShape(pipeline.task === 'zone' ? 'polygon' : 'line');
    setMode(pipeline.mode);
    setPrompt(pipeline.prompt ?? '');
    setClasses(pipeline.classes.length ? pipeline.classes : ['person']);
    setLines({ [pipeline.camera_id]: pipeline.line ?? null });
    setZones({ [pipeline.camera_id]: pipeline.zone ?? [] });
    setFlip(pipeline.flip);
    setName(pipeline.name);
    setDirection(pipeline.direction);
    setMaxCount(pipeline.max_count ? String(pipeline.max_count) : '');
    setAutoReset(pipeline.auto_reset);
    setTargetFps(pipeline.target_fps ?? 15);
    setConf(pipeline.conf ?? NGUONG_TIN_CAY_MAC_DINH);
    setSchedule(pipeline.schedule ?? DEFAULT_SCHEDULE);
    setStep(1);
    setCreating(true);
  };

  const nextStep = () => setStep((s) => Math.min(maxStep, s + 1));
  /** Khi sửa thì bước 0 (chọn camera) bị khoá, lùi nhiều nhất về bước 1. */
  const firstStep = editingId ? 1 : 0;
  const prevStep = () => setStep((s) => Math.max(firstStep, s - 1));

  const handleSave = async (startNow: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const label = effectiveTask === 'counting' ? 'Đếm qua vạch'
        : effectiveTask === 'zone' ? 'Đếm trong vùng' : 'Nhận diện';
      /** Tham số dùng chung; riêng hình vẽ thì mỗi camera một kiểu. */
      const shared = {
        task: effectiveTask,
        mode,
        prompt: mode === 'smart' ? prompt.trim() : null,
        classes,
        flip,
        // Luồng Thông minh lấy chiều đếm từ câu mô tả, và không dùng ngưỡng cảnh báo
        // hay tự đặt lại — gửi giá trị mặc định để backend không hiểu nhầm.
        direction: mode === 'smart' ? 'both' : direction,
        max_count: mode === 'smart' || !maxCount.trim() ? null : Number(maxCount),
        auto_reset: mode === 'smart' ? 'never' : autoReset,
        target_fps: targetFps,
        conf,
        schedule: schedule.enabled ? schedule : null,
      };
      const shapeOf = (cameraId: string) => ({
        line: shape === 'line' && lines[cameraId] ? lines[cameraId]! : null,
        zone: shape === 'polygon' ? zones[cameraId] ?? [] : null,
      } as { line?: LineSpec | null; zone?: ZonePoint[] | null });

      if (editingId) {
        const cameraId = cameraIds[0];
        const saved = await api.updatePipeline(editingId, {
          ...shared, ...shapeOf(cameraId),
          name: name.trim() || `${label} — ${selectedCameras[0]?.name ?? ''}`,
        });
        if (startNow && !saved.running) await api.startPipeline(saved.id);
        setSelectedPipeline(saved.id);
      } else {
        // Chọn nhiều camera thì tạo nhiều pipeline độc lập. Tên phải khác nhau, nếu
        // không thì danh sách hiện ra mấy dòng trùng tên không phân biệt được.
        const many = selectedCameras.length > 1;
        const created = [];
        for (const camera of selectedCameras) {
          const base = name.trim()
            || (mode === 'smart' ? `${label} — ${prompt.trim()}` : label);
          created.push(await api.createPipeline({
            ...shared, ...shapeOf(camera.id),
            camera_id: camera.id,
            name: many || !name.trim() ? `${base} — ${camera.name}` : base,
          }));
        }
        if (startNow) {
          for (const pipeline of created) await api.startPipeline(pipeline.id);
        }
        if (created.length) setSelectedPipeline(created[0].id);
      }

      exitWizard();
      await load();
      onChanged();
      const count = editingId ? 1 : selectedCameras.length;
      toast(
        `${editingId ? 'Đã cập nhật' : `Đã tạo ${count} pipeline`}${startNow ? ' và bắt đầu chạy' : ''}`,
      );
    } catch (err) {
      const what = editingId ? 'Không lưu được thay đổi' : 'Không tạo được pipeline';
      const msg = err instanceof Error ? `${what}: ${err.message}` : what;
      setError(msg);
      toast(msg, 'error');
    } finally {
      setBusy(false);
    }
  };

  const runAction = async (action: () => Promise<unknown>, successMsg: string) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
      onChanged();
      toast(successMsg);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Thao tác không thành công');
      toast(err instanceof Error ? err.message : 'Thao tác không thành công', 'error');
    } finally {
      setBusy(false);
    }
  };

  // Tải danh mục hỏng thì phải báo và cho thử lại. Bản trước để nguyên vòng xoay,
  // một lần hỏng là trang kẹt vĩnh viễn dù backend đã sống lại.
  if (catalogError) {
    return (
      <ErrorBanner
        message={`Không tải được danh mục bài toán: ${catalogError}`}
        onRetry={loadCatalog}
      />
    );
  }
  if (!catalog) return <SkeletonCard className="mt-4" />;

  const smartMode = catalog.modes.find((m) => m.id === 'smart');

  /* ── Chế độ tạo mới: chỉ hiện trình hướng dẫn ────────────────────────── */
  if (creating) {
    return (
      <div className="w-full space-y-3">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-800">
              {editingId ? 'Sửa pipeline' : 'Tạo pipeline mới'}
            </h1>
            <p className="text-sm text-slate-500">
              Bước {step + 1}/{maxStep + 1} · {STEPS[step]}
              {editingId && ' · camera không đổi được'}
            </p>
          </div>
          <button onClick={exitWizard} className="btn-ghost">
            <X size={14} /> Huỷ
          </button>
        </header>

        {error && <ErrorBanner message={error} onRetry={() => setError(null)} />}

        <section className="card p-4">
          <ol className="mb-4 flex items-center gap-1">
            {STEPS.map((title, index) => {
              const skipped = false;
              const done = index < step;
              const current = index === step;
              return (
                <li key={title} className="flex flex-1 items-center gap-1.5">
                  <div
                    className={`flex h-6 w-6 shrink-0 items-center justify-center
                                rounded-full text-xs font-bold ${
                      current ? 'bg-emerald-600 text-white'
                        : done ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-slate-100 text-slate-400'
                    } ${skipped ? 'opacity-40' : ''}`}
                  >
                    {done ? <Check size={11} /> : index + 1}
                  </div>
                  <span
                    className={`hidden truncate text-xs font-semibold lg:block ${
                      current ? 'text-emerald-700' : 'text-slate-400'
                    } ${skipped ? 'line-through opacity-40' : ''}`}
                  >
                    {title}
                  </span>
                  {index < STEPS.length - 1 && <div className="h-px flex-1 bg-slate-200" />}
                </li>
              );
            })}
          </ol>

          {/* Bước 1 — chọn camera, kèm màn hình xem trước bên phải */}
          {step === 0 && (
            <div className="grid gap-6 lg:grid-cols-2">
              <div>
                <span className="label">
                  Danh sách camera
                  <span className="ml-1.5 font-normal normal-case text-slate-400">
                    — chọn được nhiều, mỗi camera thành một pipeline riêng
                  </span>
                </span>
                <div className="space-y-1.5">
                  {cameras.length === 0 ? (
                    <EmptyState
                      icon={<CameraIcon size={34} />}
                      title="Chưa có camera"
                      hint="Thêm camera ở trang Giám sát trước khi tạo pipeline."
                    />
                  ) : (
                    cameras.map((camera) => {
                      const picked = cameraIds.includes(camera.id);
                      return (
                        <button
                          key={camera.id}
                          onClick={() => {
                            setCameraIds((current) => (
                              picked
                                ? current.filter((id) => id !== camera.id)
                                : [...current, camera.id]
                            ));
                            setDrawingFor(camera.id);
                          }}
                          className={`flex w-full cursor-pointer items-center gap-3
                                      rounded-lg border px-3 py-2.5 text-left
                                      transition-colors ${
                            picked
                              ? 'border-emerald-500 bg-emerald-50'
                              : 'border-slate-200 hover:border-slate-300'
                          }`}
                        >
                          <span
                            className={`flex h-4 w-4 shrink-0 items-center justify-center
                                        rounded border ${
                              picked
                                ? 'border-emerald-600 bg-emerald-600 text-white'
                                : 'border-slate-300'
                            }`}
                          >
                            {picked && <Check size={11} strokeWidth={3.5} />}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-bold text-slate-800">{camera.name}</p>
                            <p className="truncate text-xs text-slate-500">
                              {camera.location || 'Chưa đặt vị trí'}
                            </p>
                          </div>
                          <StatusDot status={camera.enabled ? camera.status : 'stopped'} />
                        </button>
                      );
                    })
                  )}
                </div>
                {cameraIds.length > 1 && (
                  <p className="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs
                                text-emerald-800">
                    Sẽ tạo <b>{cameraIds.length} pipeline</b> giống nhau về tham số, số
                    đếm tách riêng theo từng camera. Ở bước vẽ, mỗi camera phải có vạch
                    hoặc vùng của riêng nó.
                  </p>
                )}
              </div>

              <div>
                <span className="label">
                  Xem trước
                  {selectedCameras.length > 1 && (
                    <span className="ml-1.5 font-normal normal-case text-slate-400">
                      — {selectedCameras.length} camera đã chọn
                    </span>
                  )}
                </span>
                {/* Chọn nhiều camera thì vẫn chỉ một ô xem trước, kèm danh sách để bấm
                    chuyển. Mở đồng thời nhiều luồng vừa chật màn hình vừa ăn hết hạn
                    mức kết nối của trình duyệt; xem lần lượt thì mỗi lúc chỉ tốn một. */}
                {selectedCameras.length > 1 && (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {selectedCameras.map((camera) => (
                      <button
                        key={camera.id}
                        onClick={() => setDrawingFor(camera.id)}
                        className={`max-w-[13rem] truncate rounded-lg border px-2.5 py-1.5
                                    text-xs font-bold transition-colors ${
                          camera.id === drawingCamera?.id
                            ? 'border-emerald-600 bg-emerald-600 text-white'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        {camera.name}
                      </button>
                    ))}
                  </div>
                )}
                <CameraPreview camera={drawingCamera} />
              </div>
            </div>
          )}

          {/* Bước 2 — bài toán */}
          {step === 1 && (
            <div className="grid gap-2 sm:grid-cols-2">
              {catalog.tasks.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setTask(item.id)}
                  className={`cursor-pointer rounded-lg border p-3 text-left
                              transition-colors ${
                    task === item.id
                      ? 'border-emerald-500 bg-emerald-50'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <p className="text-sm font-bold text-slate-800">{item.name}</p>
                  <p className="mt-1 text-xs leading-snug text-slate-500">
                    {item.description}
                  </p>
                </button>
              ))}
            </div>
          )}

          {/* Bước 3 — luồng, đối tượng và vẽ hình trên cùng một màn */}
          {step === 2 && (
            <div className="grid gap-6 md:grid-cols-[1fr_1.15fr] md:items-start">
              {/* Cột trái: luồng và đối tượng. Cột phải có hình vẽ dính ở đầu màn
                  để lúc kéo xuống sửa tham số vẫn thấy hình đang vẽ. */}
              <div className="space-y-4">
              <ParamBox title="Luồng xử lý">
                <div className="grid gap-2 sm:grid-cols-2">
                  {catalog.modes.map((item) => (
                    <button
                      key={item.id}
                      disabled={!item.available}
                      onClick={() => setMode(item.id)}
                      className={`cursor-pointer rounded-lg border p-3 text-left
                                  transition-colors disabled:cursor-not-allowed
                                  disabled:opacity-50 ${
                        mode === item.id
                          ? 'border-emerald-500 bg-emerald-50'
                          : 'border-slate-200 hover:border-slate-300'
                      }`}
                    >
                      <p className="flex items-center gap-1.5 text-sm font-bold text-slate-800">
                        {item.id === 'smart' && (
                          <Sparkles size={13} className="text-emerald-600" />
                        )}
                        {item.name}
                      </p>
                      <p className="mt-1 text-xs leading-snug text-slate-600">
                        {item.description}
                      </p>
                    </button>
                  ))}
                </div>

                {smartMode && !smartMode.available && (
                  <p className="mt-1.5 flex items-start gap-1.5 rounded-lg bg-amber-50
                                px-2.5 py-1.5 text-xs text-amber-800">
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                    <span>
                      Chế độ Thông minh chưa sẵn sàng trên máy chủ này. Liên hệ quản trị
                      viên để cài đặt bổ sung.
                    </span>
                  </p>
                )}
              </ParamBox>

              {mode === 'smart' && (
                <div>
                  <span className="label">Mô tả đối tượng cần đếm</span>
                  <input
                    className="input"
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    placeholder="vd: người đeo ba lô đi vào"
                  />
                  <p className="mt-1 text-xs leading-snug text-slate-400">
                    {catalog.prompt_hint}
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {catalog.prompt_examples.map((example) => (
                      <button
                        key={example}
                        onClick={() => setPrompt(example)}
                        className="cursor-pointer rounded-full border border-slate-200
                                   px-2 py-0.5 text-xs font-medium text-slate-500
                                   hover:border-emerald-300 hover:text-emerald-700"
                      >
                        {example}
                      </button>
                    ))}
                  </div>

                  {preview && (
                    <div className="mt-2 flex items-center gap-1.5 rounded-lg border
                                    border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs
                                    text-emerald-800">
                      <Wand2 size={11} className="shrink-0" />
                      <span>
                        Chỉ đếm <b>{preview.filter_text}</b> · {preview.direction_label}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Luồng Thông minh không dùng tham số đếm: đối tượng được mô tả bằng
                  câu lệnh ở trên, không chọn lớp. */}
              {mode !== 'smart' && (
              <ParamBox>
                <span className="label">Đối tượng cần theo dõi</span>
                <p className="mb-1.5 text-xs text-slate-400">
                  Đã chọn <b className="text-emerald-700">{classes.length}</b>/
                  {catalog.classes.length} đối tượng
                </p>
                <div className="flex max-h-[9.5rem] flex-wrap gap-1.5 overflow-y-auto pr-1">
                  {catalog.classes.map((option) => {
                    const active = classes.includes(option.id);
                    return (
                      <button
                        key={option.id}
                        onClick={() =>
                          setClasses((current) =>
                            active
                              ? current.filter((c) => c !== option.id)
                              : [...current, option.id],
                          )
                        }
                        className={`cursor-pointer rounded-full border px-2.5 py-1
                                    text-xs font-bold transition-colors ${
                          active
                            ? 'border-emerald-600 bg-emerald-600 text-white'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        {option.name}
                      </button>
                    );
                  })}
                </div>
                {classes.length === 0 && (
                  <p className="mt-1.5 text-xs font-bold text-rose-600">
                    Chọn ít nhất một đối tượng.
                  </p>
                )}

              {effectiveTask === 'counting' && mode === 'standard' && (
                <div className="mt-4">
                  <span className="label">Hướng đếm</span>
                  <div className="grid grid-cols-3 gap-1.5">
                    {catalog.directions.map((item) => (
                      <button
                        key={item.id}
                        onClick={() => setDirection(item.id)}
                        title={item.description}
                        className={`cursor-pointer rounded-lg border px-2 py-2 text-xs
                                    font-bold transition-colors ${
                          direction === item.id
                            ? 'border-emerald-500 bg-emerald-50 text-emerald-700'
                            : 'border-slate-200 text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        {item.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {mode === 'standard' && (
              <div className="mt-4">
                <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="label" htmlFor="max-count">
                    Cảnh báo khi vượt ngưỡng
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      id="max-count"
                      type="number"
                      min={1}
                      max={999}
                      className="input"
                      value={maxCount}
                      onChange={(event) => setMaxCount(event.target.value)}
                      placeholder="để trống = tắt"
                    />
                    <span className="shrink-0 text-xs text-slate-500">đối tượng</span>
                  </div>
                </div>

                <div>
                  <label className="label" htmlFor="auto-reset">Tự động đặt lại số đếm</label>
                  <select
                    id="auto-reset"
                    className="input"
                    value={autoReset}
                    onChange={(event) => setAutoReset(event.target.value as AutoReset)}
                  >
                    {catalog.auto_resets.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </div>
                </div>
              </div>
              )}
              </ParamBox>
              )}

              <ScheduleEditor value={schedule} onChange={setSchedule} />

              <ParamBox title="Tốc độ xử lý">
                <p className="text-xs leading-snug text-slate-500">
                  Nhịp xử lý càng cao thì bám đối tượng càng mượt và đếm càng sát, đổi lại
                  tốn tài nguyên hơn. Máy yếu hoặc chạy nhiều camera thì hạ xuống.
                </p>

                <div className="mt-3 space-y-3">
                    <div>
                      <label className="label" htmlFor="target-fps">Nhịp xử lý</label>
                      <div className="flex items-center gap-2">
                        <input
                          id="target-fps"
                          type="range" min={1} max={30} step={1}
                          value={targetFps}
                          onChange={(event) => setTargetFps(Number(event.target.value))}
                          className="flex-1 accent-emerald-600"
                        />
                        <span className="w-16 shrink-0 text-right text-xs font-bold
                                         tabular-nums text-slate-700">
                          {targetFps} FPS
                        </span>
                      </div>
                      <div className="flex justify-between text-xs text-slate-400">
                        <span>Nhẹ máy, đếm sót nhiều hơn</span>
                        <span>Chính xác nhất</span>
                      </div>
                    </div>

                    <div>
                      <label className="label" htmlFor="conf">Ngưỡng tin cậy</label>
                      <div className="flex items-center gap-2">
                        <input
                          id="conf"
                          type="range" min={5} max={90} step={5}
                          value={Math.round(conf * 100)}
                          onChange={(event) => setConf(Number(event.target.value) / 100)}
                          className="flex-1 accent-emerald-600"
                        />
                        <span className="w-16 shrink-0 text-right text-xs font-bold
                                         tabular-nums text-slate-700">
                          {Math.round(conf * 100)}%
                        </span>
                      </div>
                      <div className="flex justify-between text-xs text-slate-400">
                        <span>Bắt nhiều, dễ nhầm</span>
                        <span>Bắt ít, chắc chắn</span>
                      </div>
                    </div>

                    <div>
                      <label className="label" htmlFor="tracker">Thuật toán bám đuổi</label>
                      <select id="tracker" className="input" disabled defaultValue="bytetrack">
                        {catalog.trackers.map((item) => (
                          <option key={item.id} value={item.id}>{item.name}</option>
                        ))}
                      </select>
                    </div>
                </div>
              </ParamBox>
              </div>

              {/* Cột phải: bỏ sticky để khung vẽ ngang hàng với box cột trái ở mọi
                  vị trí cuộn. */}
              <div>
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <div className="mb-2">
                    <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
                      Vẽ trên khung hình
                    </h3>
                  </div>

                {/* Chọn nhiều camera thì vẽ lần lượt từng cái. Chấm cạnh tên cho biết
                    camera nào đã có hình, camera nào còn thiếu. */}
                {needsShape && selectedCameras.length > 1 && (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {selectedCameras.map((camera) => {
                      const done = !missingShape.some((c) => c.id === camera.id);
                      const current = camera.id === drawingCamera?.id;
                      return (
                        <button
                          key={camera.id}
                          onClick={() => setDrawingFor(camera.id)}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5
                                      py-1.5 text-xs font-bold transition-colors ${
                            current
                              ? 'border-emerald-600 bg-emerald-600 text-white'
                              : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                          }`}
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              done ? 'bg-emerald-400'
                                : current ? 'bg-white/70' : 'bg-amber-400'
                            }`}
                          />
                          {camera.name}
                        </button>
                      );
                    })}
                  </div>
                )}
                {needsShape && missingShape.length > 0 && selectedCameras.length > 1 && (
                  <p className="mb-2 text-xs font-bold text-amber-700">
                    Còn {missingShape.length} camera chưa vẽ:{' '}
                    {missingShape.map((c) => c.name).join(', ')}
                  </p>
                )}

                {needsShape && drawingCamera ? (
                  <ShapeDrawer
                    key={drawingCamera.id}
                    cameraId={drawingCamera.id}
                    shape={shape}
                    line={lines[drawingCamera.id] ?? null}
                    zone={zones[drawingCamera.id] ?? []}
                    flip={flip}
                    onLineChange={(value) =>
                      setLines((current) => ({ ...current, [drawingCamera.id]: value }))}
                    onZoneChange={(value) =>
                      setZones((current) => ({ ...current, [drawingCamera.id]: value }))}
                    onFlipChange={setFlip}
                    onShapeChange={setShape}
                  />
                ) : (
                  <div className="flex aspect-video items-center justify-center rounded-xl
                                  border border-dashed border-slate-300 bg-slate-50
                                  px-6 text-center text-sm text-slate-400">
                    Bài toán nhận diện không cần vẽ vạch hay vùng — hệ thống theo dõi
                    toàn bộ khung hình.
                  </div>
                )}
                </div>
              </div>
            </div>
          )}

          {/* Bước 4 — kiểm tra, kèm khung hình có hình vẽ để soát lại lần cuối */}
          {step === 3 && (
            <div className="grid gap-6 lg:grid-cols-2">
              <div>
                <span className="label">
                  {needsShape ? 'Hình đã vẽ trên khung camera' : 'Khung hình camera'}
                </span>
                {selectedCameras.length > 1 && (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {selectedCameras.map((camera) => (
                      <button
                        key={camera.id}
                        onClick={() => setDrawingFor(camera.id)}
                        className={`rounded-lg border px-2.5 py-1.5 text-xs font-bold
                                    transition-colors ${
                          camera.id === drawingCamera?.id
                            ? 'border-emerald-600 bg-emerald-600 text-white'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        {camera.name}
                      </button>
                    ))}
                  </div>
                )}
                {drawingCamera && needsShape ? (
                  <ShapeDrawer
                    readOnly
                    key={drawingCamera.id}
                    cameraId={drawingCamera.id}
                    shape={shape}
                    line={lines[drawingCamera.id] ?? null}
                    zone={zones[drawingCamera.id] ?? []}
                    flip={flip}
                    onLineChange={() => {}}
                    onZoneChange={() => {}}
                    onFlipChange={setFlip}
                    onShapeChange={setShape}
                  />
                ) : (
                  <CameraPreview camera={drawingCamera} />
                )}
              </div>

            <div className="space-y-3">
              <div>
                <label className="label" htmlFor="pipeline-name">Tên pipeline</label>
                <input
                  id="pipeline-name"
                  className="input"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder={`${taskDef?.name ?? ''} — ${selectedCameras[0]?.name ?? ''}`}
                />
                {selectedCameras.length > 1 && (
                  <p className="mt-1 text-xs text-slate-500">
                    Tên camera được ghép vào sau để {selectedCameras.length} pipeline
                    không trùng tên nhau.
                  </p>
                )}
              </div>

              <dl className="divide-y divide-slate-100 rounded-lg border border-slate-200
                             text-xs">
                <Row
                  label={selectedCameras.length > 1
                    ? `Camera (${selectedCameras.length})` : 'Camera'}
                  value={selectedCameras.map((c) => c.name).join(', ') || '—'}
                />
                <Row label="Bài toán" value={taskDef?.name ?? task} />
                <Row
                  label="Luồng"
                  value={catalog.modes.find((m) => m.id === mode)?.name ?? mode}
                />
                {mode === 'smart' && <Row label="Mô tả" value={prompt.trim() || '—'} />}
                {mode === 'smart' && preview && (
                  <Row label="Chiều đếm" value={preview.direction_label} />
                )}
                <Row
                  label="Đối tượng"
                  value={classes
                    .map((c) => catalog.classes.find((o) => o.id === c)?.name ?? c)
                    .join(', ')}
                />
                {/* Không liệt kê toạ độ vạch: hình vẽ đã hiện ngay bên trái, đọc
                    bốn con số thập phân không nói thêm được gì. */}
                {needsShape && shape === 'polygon' && drawingCamera && (
                  <Row
                    label="Vùng"
                    value={`đa giác ${zones[drawingCamera.id]?.length ?? 0} đỉnh`}
                  />
                )}
                {effectiveTask === 'counting' && mode === 'standard' && (
                  <Row
                    label="Hướng đếm"
                    value={catalog.directions.find((d) => d.id === direction)?.name ?? direction}
                  />
                )}
                {mode === 'standard' && (
                  <Row
                    label="Cảnh báo vượt ngưỡng"
                    value={maxCount.trim() ? `${maxCount} đối tượng` : 'Tắt'}
                  />
                )}
                {mode === 'standard' && (
                  <Row
                    label="Tự đặt lại số đếm"
                    value={catalog.auto_resets.find((a) => a.id === autoReset)?.name ?? autoReset}
                  />
                )}
                <Row
                  label="Tốc độ xử lý"
                  value={`${targetFps} FPS · tin cậy ${Math.round(conf * 100)}%`}
                />
                <Row
                  label="Lịch chạy"
                  value={
                    schedule.enabled
                      ? schedule.slots
                          .map((s) => `${s.days.length} ngày ${s.from}–${s.to}`)
                          .join('; ')
                      : 'Liên tục 24/7'
                  }
                />
              </dl>

              {mode === 'smart' && (
                <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed
                              text-slate-500">
                  Lần chạy đầu mất khoảng 10–15 giây để hệ thống chuẩn bị. Sau đó mỗi
                  đối tượng chỉ được kiểm tra một lần rồi ghi nhớ kết quả, nên luồng
                  video vẫn chạy mượt.
                </p>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => handleSave(true)}
                  disabled={busy}
                  className="btn-primary flex-1 !py-2.5"
                >
                  <Play size={14} /> Lưu và chạy ngay
                </button>
                <button
                  onClick={() => handleSave(false)}
                  disabled={busy}
                  className="btn-ghost !py-2.5"
                >
                  Chỉ lưu
                </button>
              </div>
            </div>
            </div>
          )}

          <div className="mt-4 flex items-center justify-between border-t
                          border-slate-100 pt-3">
            <button onClick={prevStep} disabled={step === firstStep} className="btn-ghost">
              <ChevronLeft size={14} /> Quay lại
            </button>
            {step < maxStep && (
              <button onClick={nextStep} disabled={!canAdvance} className="btn-primary">
                Tiếp tục <ChevronRight size={14} />
              </button>
            )}
          </div>
        </section>
      </div>
    );
  }

  /* ── Chế độ danh sách ────────────────────────────────────────────────── */
  return (
    <div className="space-y-3">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-800">Cấu hình AI</h1>
          <p className="text-xs text-slate-500">
            {pipelines.length} pipeline · {pipelines.filter((p) => p.running).length} đang chạy
          </p>
        </div>
        <button onClick={() => setCreating(true)} className="btn-primary">
          <Plus size={14} /> Tạo pipeline mới
        </button>
      </header>

      {error && <ErrorBanner message={error} onRetry={() => setError(null)} />}

      <div className="grid gap-3">
        <div className="card">
          <div className="card-head">
            <span className="card-head-title">Pipeline đã tạo</span>
          </div>
          {pipelines.length === 0 ? (
            <EmptyState
              icon={<Cpu size={32} />}
              title="Chưa có pipeline nào"
              hint="Bấm “Tạo pipeline mới” để bắt đầu."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
                  <tr>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">Tên</th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">Camera</th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">Bài toán</th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">Chế độ</th>
                    <th className="px-3 py-2 font-semibold uppercase tracking-wide">Trạng thái</th>
                    <th className="px-3 py-2 text-right font-semibold uppercase tracking-wide">
                      Thao tác
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {pipelines.map((pipeline) => (
                    <PipelineRow
                      key={pipeline.id}
                      pipeline={pipeline}
                      cameraName={cameras.find((c) => c.id === pipeline.camera_id)?.name}
                      selected={selectedPipeline === pipeline.id}
                      busy={busy}
                      onSelect={() => setSelectedPipeline(pipeline.id)}
                      onStart={() => runAction(
                        () => api.startPipeline(pipeline.id),
                        `Đã chạy pipeline "${pipeline.name}"`,
                      )}
                      onStop={() => runAction(
                        () => api.stopPipeline(pipeline.id),
                        `Đã dừng pipeline "${pipeline.name}"`,
                      )}
                      onEdit={() => startEdit(pipeline)}
                      onDelete={() => runAction(
                        () => api.deletePipeline(pipeline.id),
                        `Đã xoá pipeline "${pipeline.name}"`,
                      )}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

/** Màn hình xem trước camera. Dùng luồng trực tiếp nếu camera đang bật, không thì ảnh tĩnh. */
function CameraPreview({ camera }: { camera: Camera | null }) {
  if (!camera) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-xl border
                      border-dashed border-slate-300 bg-slate-50 px-6 text-center
                      text-sm text-slate-400">
        Chọn một camera ở danh sách bên trái để xem trước
      </div>
    );
  }

  const isLive = camera.enabled && camera.status === 'online';
  return (
    <div className="overflow-hidden rounded-xl border border-slate-300">
      <div className="relative aspect-video bg-slate-950">
        {isLive ? (
          <StreamImage
            key={camera.id}
            src={api.streamUrl(camera.id, camera.id, true)}
            alt={camera.name}
            className="absolute inset-0 h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2
                          text-sm text-slate-500">
            <CameraIcon size={28} />
            <p className="font-bold">
              {camera.enabled ? 'Đang kết nối…' : 'Camera đang tắt'}
            </p>
            <p className="max-w-[80%] text-center text-xs text-slate-600">
              {camera.enabled
                ? 'Chờ luồng video sẵn sàng.'
                : 'Bật camera ở trang Giám sát để xem trước. Vẫn tạo được pipeline.'}
            </p>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 bg-white px-3 py-2">
        <span className="truncate text-sm font-bold text-slate-800">{camera.name}</span>
        <span className="shrink-0 text-xs text-slate-400">
          {isLive ? `${camera.fps} FPS · ${camera.resolution}` : camera.location || '—'}
        </span>
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4 px-3 py-1.5">
      <dt className="shrink-0 text-slate-500">{label}</dt>
      <dd className={`text-right font-bold text-slate-800 ${mono ? 'font-mono' : ''}`}>
        {value}
      </dd>
    </div>
  );
}

function PipelineRow({
  pipeline, cameraName, selected, busy, onSelect, onStart, onStop, onEdit, onDelete,
}: {
  pipeline: Pipeline; cameraName?: string; selected: boolean; busy: boolean;
  onSelect: () => void; onStart: () => void; onStop: () => void;
  onEdit: () => void; onDelete: () => void;
}) {
  const isSmart = pipeline.mode === 'smart';
  const taskLabel = pipeline.task === 'counting' ? 'Đếm qua vạch'
    : pipeline.task === 'zone' ? 'Đếm trong vùng' : 'Nhận diện';

  return (
    <tr
      onClick={onSelect}
      className={`cursor-pointer align-top transition-colors ${
        selected ? 'bg-emerald-50/60' : 'hover:bg-slate-50'
      }`}
    >
      <td className="px-3 py-2">
        <p className="flex items-center gap-1.5 font-bold text-slate-800">
          {isSmart && <Sparkles size={11} className="shrink-0 text-emerald-600" />}
          {pipeline.name}
        </p>
        {isSmart && pipeline.prompt && (
          <p className="mt-0.5 italic text-emerald-700">“{pipeline.prompt}”</p>
        )}
      </td>

      <td className="px-3 py-2 text-slate-600">{cameraName ?? pipeline.camera_id}</td>
      <td className="px-3 py-2 text-slate-600">{taskLabel}</td>
      <td className="px-3 py-2 text-slate-600">
        {isSmart ? 'Thông minh' : 'Tiêu chuẩn'}
      </td>

      <td className="px-3 py-2">
        <span className={pipeline.running ? 'badge-on' : 'badge-off'}>
          {pipeline.running ? 'Đang chạy' : 'Đã dừng'}
        </span>
      </td>

      <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-end gap-1">
          {pipeline.running ? (
            <button onClick={onStop} disabled={busy}
                    className="btn-ghost !px-2 !py-0.5 !text-xs">
              <Square size={10} /> Dừng
            </button>
          ) : (
            <button onClick={onStart} disabled={busy}
                    className="btn-primary !px-2 !py-0.5 !text-xs">
              <Play size={10} /> Chạy
            </button>
          )}
          <button onClick={onEdit} disabled={busy}
                  className="btn-ghost !px-2 !py-0.5 !text-xs"
                  title="Sửa cấu hình pipeline">
            <Pencil size={10} /> Sửa
          </button>
          <button onClick={onDelete} disabled={busy}
                  className="btn-danger !px-2 !py-0.5 !text-xs" title="Xoá pipeline">
            <Trash2 size={10} />
          </button>
        </div>
      </td>
    </tr>
  );
}
