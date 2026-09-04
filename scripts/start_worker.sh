#!/usr/bin/env bash
# Dedicated terminal for crawl jobs, automatic scheduling and Google Sheets writes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
elif [ -x "/home/reg/miniconda3/bin/python3" ]; then
    PYTHON_BIN="/home/reg/miniconda3/bin/python3"
elif [ -n "${CONDA_PREFIX:-}" ] && [ -x "$CONDA_PREFIX/bin/python3" ]; then
    PYTHON_BIN="$CONDA_PREFIX/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    PYTHON_BIN="python"
fi

echo "======================================================================"
echo "MIO Crawl Worker"
echo "======================================================================"
echo "Nhận job từ FE · chạy lịch tự động · crawl/AI · ghi trực tiếp SQLite (leads.db)"
echo "Python: $PYTHON_BIN"
echo "Dừng an toàn bằng Ctrl+C"
echo "======================================================================"

"$PYTHON_BIN" -c "from app.database import init_db; init_db()"
exec "$PYTHON_BIN" -m scripts.crawl_worker "$@"
