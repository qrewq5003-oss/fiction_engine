#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Запуск Fiction Engine на порту 5000..."
cd "$SCRIPT_DIR/fiction_engine/web"
python app.py &
FE_PID=$!

echo "🗂 Запуск Планировщика на порту 5001..."
cd "$SCRIPT_DIR/planner"
python app.py &
PLANNER_PID=$!

echo ""
echo "✅ Fiction Engine:  http://localhost:5000"
echo "   Планировщик:     http://localhost:5001"
echo ""
echo "Нажми Ctrl+C чтобы остановить оба"

trap "kill $FE_PID $PLANNER_PID 2>/dev/null; exit 0" INT TERM
wait
