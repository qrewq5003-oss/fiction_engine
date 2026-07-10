#!/bin/bash
# Запуск Fiction Engine

cd "$(dirname "$0")"

echo ""
echo "  ┌─────────────────────────────┐"
echo "  │  Fiction Engine запускается  │"
echo "  └─────────────────────────────┘"
echo ""

# Инициализировать БД если нужно
python3 -c "
import sys; sys.path.insert(0, '.')
from engine.db import init_db
init_db()
"

# Проверить ключи
has_keys=$(python3 -c "
import sys; sys.path.insert(0, '.')
from engine.db import get_api_key
a = get_api_key('anthropic_direct')
n = get_api_key('nano_gpt')
print('ok' if (a or n) else 'no')
" 2>/dev/null || echo "no")

if [ "$has_keys" = "no" ]; then
    echo "  ⚠  Нет API ключей. Добавь через терминал:"
    echo "     python3 cli.py keys"
    echo ""
fi

# Выбор режима
echo "  Как запустить?"
echo "  1. Браузер (веб-интерфейс) — http://localhost:5000"
echo "  2. Терминал (CLI)"
echo "  3. Оба одновременно"
echo ""
read -p "  Выбор (1/2/3): " choice

case "$choice" in
  1)
    echo "  › Запускаю веб-сервер..."
    python3 web/app.py
    ;;
  2)
    python3 cli.py
    ;;
  3)
    echo "  › Запускаю веб-сервер в фоне..."
    python3 web/app.py &
    WEB_PID=$!
    sleep 1
    echo "  ✓ Веб: http://localhost:5000"
    echo ""
    python3 cli.py
    kill $WEB_PID 2>/dev/null
    ;;
  *)
    python3 web/app.py
    ;;
esac
