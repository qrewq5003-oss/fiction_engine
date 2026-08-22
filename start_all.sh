#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# python3, а не python: во многих дистрибутивах голого `python` нет.
# Если рядом есть .venv из setup.sh — используем его.
if [ -x "$SCRIPT_DIR/fiction_engine/.venv/bin/python" ]; then
    PY="$SCRIPT_DIR/fiction_engine/.venv/bin/python"
else
    PY="python3"
fi

echo "🚀 Запуск Fiction Engine на порту 5000..."
cd "$SCRIPT_DIR/fiction_engine/web"
"$PY" app.py &
FE_PID=$!

echo "🗂 Запуск Планировщика на порту 5001..."
cd "$SCRIPT_DIR/planner"
"$PY" app.py &
PLANNER_PID=$!

echo ""
echo "✅ Fiction Engine:  http://localhost:5000"
echo "   Планировщик:     http://localhost:5001"
echo ""
echo "Нажми Ctrl+C чтобы остановить оба"

trap "kill $FE_PID $PLANNER_PID 2>/dev/null; exit 0" INT TERM
wait
