#!/bin/bash
# Установка Fiction Engine

set -e

echo ""
echo "  ╔══════════════════════════╗"
echo "  ║   Fiction Engine Setup   ║"
echo "  ╚══════════════════════════╝"
echo ""

# Проверить Python 3.10+
python_version=$(python3 -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
if [ "$python_version" = "False" ]; then
    echo "  ✗ Нужен Python 3.10+. Текущая: $(python3 --version)"
    exit 1
fi
echo "  ✓ Python: $(python3 --version)"

# Установить зависимости
echo "  › Устанавливаю зависимости..."
pip3 install anthropic openai flask python-dotenv --quiet --break-system-packages 2>/dev/null || \
pip3 install anthropic openai flask python-dotenv --quiet

echo "  ✓ Зависимости установлены"

# Создать .env если нет
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
    else
        # Генерируем минимальный .env с случайным ключом
        SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        echo "FLASK_SECRET_KEY=$SECRET" > .env
    fi
    echo "  ✓ Создан .env"
else
    echo "  ✓ .env уже существует"
fi

# Создать папку проекта
mkdir -p ~/fiction_engine/prompts_out
echo "  ✓ Папка ~/fiction_engine готова"

# Инициализировать БД
cd "$(dirname "$0")"
python3 -c "
import sys; sys.path.insert(0, '.')
from engine.db import init_db
init_db()
print('  ✓ База данных инициализирована')
"

echo ""
echo "  ══════════════════════════════════"
echo "  Готово! Следующие шаги:"
echo ""
echo "  1. Добавь API ключи:"
echo "     python3 cli.py keys"
echo ""
echo "  2. Запусти интерфейс:"
echo "     python3 cli.py              ← терминал"
echo "     python3 web/app.py          ← браузер (localhost:5000)"
echo ""
echo "  Или сразу всё:"
echo "     bash run.sh"
echo "  ══════════════════════════════════"
echo ""
