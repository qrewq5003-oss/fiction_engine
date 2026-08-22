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
# На системах с неизменяемым /usr (SteamOS, Fedora Silverblue) pip в систему
# не ставится вовсе — там единственный рабочий путь это venv.
echo "  › Устанавливаю зависимости..."
if [ -d ".venv" ]; then
    echo "  › Использую существующий .venv"
elif python3 -m venv .venv 2>/dev/null; then
    echo "  ✓ Создано окружение .venv"
else
    echo "  ⚠ Не удалось создать venv — пробую системный pip"
fi

if [ -x ".venv/bin/pip" ]; then
    .venv/bin/pip install -q -r requirements.txt
    PY=".venv/bin/python"
    echo "  ✓ Зависимости установлены в .venv (запуск: .venv/bin/python web/app.py)"
else
    python3 -m pip install -q -r requirements.txt --break-system-packages 2>/dev/null || \
    python3 -m pip install -q -r requirements.txt || {
        echo "  ✗ Не удалось установить зависимости."
        echo "    Создайте окружение вручную:"
        echo "      python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
        exit 1
    }
    PY="python3"
fi

echo "  ✓ Зависимости установлены"

# Создать .env если нет
SECRET_PLACEHOLDER="замени-на-случайную-строку"

if [ ! -f ".env" ]; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    if [ -f ".env.example" ]; then
        # Копируем шаблон, но ключ подставляем настоящий: раньше сюда
        # попадал плейсхолдер из .env.example — то есть общеизвестная
        # строка из репозитория подписывала сессии.
        sed "s|^FLASK_SECRET_KEY=.*|FLASK_SECRET_KEY=$SECRET|" .env.example > .env
    else
        echo "FLASK_SECRET_KEY=$SECRET" > .env
    fi
    echo "  ✓ Создан .env со случайным FLASK_SECRET_KEY"
else
    if grep -q "$SECRET_PLACEHOLDER" .env 2>/dev/null; then
        SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        sed -i "s|^FLASK_SECRET_KEY=.*|FLASK_SECRET_KEY=$SECRET|" .env
        echo "  ✓ В .env стоял плейсхолдер — заменён случайным ключом"
    else
        echo "  ✓ .env уже существует"
    fi
fi

# Создать папку проекта
mkdir -p ~/fiction_engine/prompts_out
echo "  ✓ Папка ~/fiction_engine готова"

# Инициализировать БД
cd "$(dirname "$0")"
"${PY:-python3}" -c "
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
