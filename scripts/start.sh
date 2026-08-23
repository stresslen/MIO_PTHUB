#!/usr/bin/env bash
# ==============================================================================
# One-Click Start Script for AI Lead Intelligence & Crawler System
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "======================================================================"
echo "🚀 Starting AI Lead Intelligence & Crawler System"
echo "======================================================================"

# Auto-detect Python binary with installed dependencies
if [ -x "/home/reg/miniconda3/bin/python3" ]; then
    PYTHON_BIN="/home/reg/miniconda3/bin/python3"
elif [ -n "$CONDA_PREFIX" ] && [ -x "$CONDA_PREFIX/bin/python3" ]; then
    PYTHON_BIN="$CONDA_PREFIX/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    PYTHON_BIN="python"
fi

echo "[*] Using Python: $PYTHON_BIN"

# 1. Initialize Database Tables (Chỉ tạo bảng nếu chưa có, bảo toàn 100% dữ liệu cũ)
$PYTHON_BIN -c "from app.database import init_db; init_db();"

# 2. Check existing database records
LEAD_COUNT=$($PYTHON_BIN -c "from app.database import SessionLocal; from app.models.lead import Lead; db=SessionLocal(); print(db.query(Lead).count()); db.close()")
echo "[*] Dữ liệu hiện có trong Database: $LEAD_COUNT leads (Dữ liệu được bảo toàn)"

# 3. Start FastAPI Server & Automated Daily Scheduler
echo "======================================================================"
echo "🌟 Web Dashboard: http://127.0.0.1:8000"
echo "⏰ Daily Scheduler: Tự động chạy ngầm 06:00 AM mỗi ngày"
echo "📖 Swagger API Docs: http://127.0.0.1:8000/docs"
echo "======================================================================"
exec $PYTHON_BIN -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app --reload-dir static --reload-dir configs
