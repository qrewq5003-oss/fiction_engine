#!/usr/bin/env python3
"""
scoping.py — запись в таблицу проекта обязана ограничиваться проектом.

Зачем
─────
Утечки принадлежности в Fiction Engine рождались не в обработчиках, а
в слое БД. Функция выглядела безобидно:

    def delete_symbol(symbol_id: int):
        conn.execute("DELETE FROM symbols WHERE id=?", (symbol_id,))

Идентификатор символа уникален на всю базу, поэтому обработчик, взявший
его из тела запроса, удалял символ ЛЮБОГО проекта. Так были найдены
семь маршрутов: чужой эталон, чужой профиль голоса, чужой символ,
чужое ожидающее обновление состояния.

Чинить каждый обработчик — чинить перечень: следующий напишут без
проверки. Правило работает на уровень ниже: пока в SQL нет
`project_id`, функцию нельзя вызвать безопасно, сколько бы проверок
ни стояло выше.

Правило
───────
Если функция выполняет DELETE или UPDATE по таблице, в которой есть
колонка project_id, то в тексте этого же запроса должен встречаться
project_id. Таблицы берутся из схемы, а не из списка в этом файле:
новая таблица с project_id попадает под правило сама.

Запуск:
    python tools/scoping.py          # 0 — чисто, 1 — есть нарушения
"""

from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "fiction_engine"

WRITE = re.compile(r"\b(DELETE\s+FROM|UPDATE)\s+([A-Za-z_][A-Za-z_0-9]*)", re.IGNORECASE)


def scoped_tables() -> set[str]:
    """Таблицы с колонкой project_id — прямо из схемы приложения."""
    sys.path.insert(0, str(APP))
    from unittest.mock import MagicMock
    for mod in ("openai", "anthropic"):
        sys.modules.setdefault(mod, MagicMock())
    import engine.db_core as dbc
    dbc.DB_PATH = Path(tempfile.mkdtemp()) / "schema.db"
    dbc.init_db()
    with dbc.get_conn() as conn:
        names = [t for (t,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        return {t for t in names
                if any(c[1] == "project_id" for c in conn.execute(f"PRAGMA table_info({t})"))}


def sql_strings(node: ast.AST) -> list[str]:
    """Все строковые литералы внутри узла, включая склеенные и f-строки."""
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def check_file(path: Path, tables: set[str]) -> list[tuple[int, str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call):
                continue
            for sql in sql_strings(call):
                for verb, table in WRITE.findall(sql):
                    if table not in tables:
                        continue
                    if re.search(r"\bproject_id\b", sql, re.IGNORECASE):
                        continue
                    bad.append((call.lineno, fn.name,
                                f"{verb.upper()} {table} без project_id"))
    return bad


def main() -> int:
    tables = scoped_tables()
    findings = []
    for path in sorted(APP.glob("engine/db*.py")):
        for lineno, fn, msg in check_file(path, tables):
            findings.append((path.relative_to(ROOT), lineno, fn, msg))

    if not findings:
        print(f"✓ scoping: запись в {len(tables)} таблиц проекта ограничена project_id")
        return 0

    print(f"✗ scoping: {len(findings)} записей в таблицу проекта без project_id\n")
    for rel, lineno, fn, msg in findings:
        print(f"  {rel}:{lineno}  {fn}()")
        print(f"      {msg}")
        print(f"      Объект чужого проекта будет изменён, если его id придёт извне.")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
