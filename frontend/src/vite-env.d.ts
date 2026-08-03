/// <reference types="vite/client" />

/** Biến môi trường của Vite mà mã nguồn đọc tới. */
interface ImportMetaEnv {
  /**
   * Địa chỉ gốc phát luồng video khi chạy phát triển.
   *
   * Mặc định là `http://localhost:8000`. Đặt lại khi backend nghe ở cổng khác, ví dụ
   * `VITE_STREAM_ORIGIN=http://localhost:8001 npm run dev`.
   */
  readonly VITE_STREAM_ORIGIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
