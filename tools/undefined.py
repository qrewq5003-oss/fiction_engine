#!/usr/bin/env python3
"""
undefined.py — поиск обращений к несуществующим именам.

Зачем отдельный инструмент. Хелпер `_fe_base_url()` вызывался в шести
местах планировщика и не был определён вовсе: функцию снесли правкой
соседнего блока. Все обращения падали с NameError, причём четыре из пяти
маскировались под «Fiction Engine не запущен» — вокруг стоял широкий
перехват, а NameError тоже Exception.

55 тестов остались зелёными: ни один не исполнял эти строки. Такую
ошибку ловит статический анализ мгновенно и бесплатно.

Проверяются только неопределённые имена: неиспользуемые импорты и прочий
шум pyflakes не мешают, их отсеиваем.

Запуск:
    python3 tools/undefined.py fiction_engine planner
"""

import subprocess
import sys
from pathlib import Path

_SKIP_DIRS = ("__pycache__", ".venv", "venv", "site-packages",
              ".mypy_cache", ".pytest_cache", ".hypothesis", ".git",
              "build", "dist")

# Интересуют только сообщения об обращении к тому, чего нет
_WANTED = ("undefined name", "undefined local")


def _files(roots: list[str]) -> list[str]:
    out = []
    for root in roots:
        for p in Path(root).rglob("*.py"):
            if not any(part in _SKIP_DIRS for part in p.parts):
                out.append(str(p))
    return sorted(out)


def main() -> int:
    roots = sys.argv[1:] or ["."]
    files = _files(roots)
    if not files:
        print("Файлов не найдено")
        return 0

    proc = subprocess.run([sys.executable, "-m", "pyflakes", *files],
                          capture_output=True, text=True)

    # Отсутствие pyflakes НЕ должно выглядеть как «всё чисто»: инструмент
    # обязан честно сказать, что не проверял. Первая версия этого не
    # делала и молча возвращала ноль проблем — та же болезнь, ради
    # которой инструмент и написан.
    if "No module named pyflakes" in proc.stderr:
        print("pyflakes не установлен: pip install pyflakes", file=sys.stderr)
        return 2

    problems = [line for line in proc.stdout.splitlines()
                if any(mark in line for mark in _WANTED)]

    print(f"Проверено файлов: {len(files)}")
    print(f"Неопределённых имён: {len(problems)}\n")
    for line in problems:
        print("  " + line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
