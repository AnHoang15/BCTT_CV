#!/bin/bash
# ── Khởi chạy BCTT (Backend + Cloudflare Tunnel) ──────────────────────────────
# Usage:
#   ./start.sh              — chạy backend + tunnel (miễn phí, không cần tài khoản)
#   ./start.sh --no-tunnel  — chỉ chạy backend
#   ./start.sh --local      — chạy backend + frontend dev server (localhost)
# ───────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/backend/.venv/bin/python"
PORT="${API_PORT:-8000}"
NO_TUNNEL=false
LOCAL=false

for arg in "$@"; do
  case "$arg" in
    --no-tunnel) NO_TUNNEL=true ;;
    --local)     LOCAL=true ;;
    --help|-h)
      echo "Usage: $0 [--no-tunnel] [--local]"
      echo "  --no-tunnel  Chỉ chạy backend, không mở tunnel"
      echo "  --local      Chạy backend + frontend dev server (localhost)"
      exit 0 ;;
  esac
done

# ── Kill processes cũ trên port ────────────────────────────────────────────────
cleanup() {
  echo ""
  echo "Đang dừng..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  [ -n "$TUNNEL_PID" ]  && kill "$TUNNEL_PID" 2>/dev/null
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  wait 2>/dev/null
  echo "Đã dừng."
}
trap cleanup EXIT INT TERM

# ── Kill port cũ ──────────────────────────────────────────────────────────────
lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
sleep 0.5

# ── Build frontend nếu chưa có ────────────────────────────────────────────────
if [ ! -f frontend/dist/index.html ]; then
  echo "Building frontend..."
  cd frontend && npm run build && cd ..
fi

# ── Chạy backend ──────────────────────────────────────────────────────────────
echo "Khởi động backend trên port $PORT ..."
cd backend
"$VENV" run.py --port "$PORT" &
BACKEND_PID=$!
cd ..

# Đợi backend sẵn sàng
echo -n "Đợi backend "
for i in $(seq 1 30); do
  if curl -s "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
    echo " ✅"
    break
  fi
  echo -n "."
  sleep 1
done

# ── Frontend dev server (optional) ────────────────────────────────────────────
if [ "$LOCAL" = true ]; then
  echo "Khởi động frontend dev server trên port 3000..."
  cd frontend && npm run dev &
  FRONTEND_PID=$!
  cd ..
fi

# ── Cloudflare Tunnel ─────────────────────────────────────────────────────────
if [ "$NO_TUNNEL" = false ] && [ "$LOCAL" = false ]; then
  if ! command -v cloudflared &> /dev/null; then
    echo "⚠️  cloudflared chưa cài. Cài bằng:"
    echo "   brew install cloudflared"
    echo "   Hoặc chạy: ./start.sh --no-tunnel"
    echo ""
    echo "Backend đang chạy tại: http://localhost:$PORT"
    wait $BACKEND_PID
    exit 1
  fi

  echo "Mở Cloudflare Tunnel..."
  cloudflared tunnel --url "http://localhost:$PORT" --no-autoupdate 2>&1 | while IFS= read -r line; do
    # Extract tunnel URL from cloudflared output
    if echo "$line" | grep -qo 'https://[^ ]*\.trycloudflare\.com'; then
      TUNNEL_URL=$(echo "$line" | grep -o 'https://[^ ]*\.trycloudflare\.com')
      echo ""
      echo "═══════════════════════════════════════════════════════════════"
      echo "  🔗 Tunnel URL: $TUNNEL_URL"
      echo "  📱 Chia sẻ link này cho người khác truy cập"
      echo "  ⏹  Nhấn Ctrl+C để dừng"
      echo "═══════════════════════════════════════════════════════════════"
      echo ""
    fi
    echo "$line"
  done &
  TUNNEL_PID=$!
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  🖥  Backend:     http://localhost:$PORT"
[ "$LOCAL" = true ] && echo "  🌐 Frontend:    http://localhost:3000"
echo "  📖 API Docs:    http://localhost:$PORT/docs"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Nhấn Ctrl+C để dừng"

wait $BACKEND_PID 2>/dev/null || true
