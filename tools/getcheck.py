#!/usr/bin/env python3
"""
getcheck.py — GET-обработчик не должен менять данные.

Повод. Класс-тесты принадлежности отбирают маршруты по методу и по именам
параметров, поэтому GET-обработчик, меняющий данные, мимо перебора
проходил: один и тот же обработчик ловился или нет в зависимости от того,
назван параметр `scene_id` или `sid`. Отбор — отдельный разговор; эта
проверка закрывает другую сторону того же места, семантику GET.

Почему это стоит проверять независимо от принадлежности. GET обязан быть
безопасным: браузер волен сходить по такому адресу без ведома
пользователя — предзагрузка ссылки, восстановление вкладок, переход по
истории. Обработчик, который при этом пишет в базу, срабатывает в
моменты, которых никто не запрашивал.

Правило. Обработчик, объявленный без `methods` (то есть GET) или только с
безопасными методами, не должен по цепочке вызовов достигать функции,
выполняющей INSERT / UPDATE / DELETE / REPLACE.

DDL записью не считается: `CREATE TABLE IF NOT EXISTS` в начале страницы —
идемпотентная подготовка схемы, данные она не меняет. На этом коде выбор
ни на что не влияет — с включённым DDL находки те же, проверено; так что
это решение о смысле, а не способ убрать шум.

SQL ищется в строковых литералах, а не в тексте функции: упоминание
«исторически здесь был DELETE FROM» в докстринге иначе делает функцию
пишущей. Проверено пробой — так и было.

Цепочка вызовов печатается целиком: нарушение обычно лежит не в самом
обработчике, а через две-три функции от него.

Запуск:
    python3 tools/getcheck.py fiction_engine planner
"""

import ast
import re
import sys
from collections import deque
from pathlib import Path

# build/dist — копия приложения, оставшаяся от сборки. Она не в git
# (лежит в .gitignore), но есть на диске у любого, кто собирал пакет,
# и устаревает молча: та же находка печаталась дважды, второй раз из
# кода, которого в репозитории нет. Так же исключают её sigcheck,
# undefined, pitfalls и dead.
_SKIP_DIRS = ("__pycache__", ".venv", "venv", "site-packages",
              ".mypy_cache", ".pytest_cache", ".git", "tests",
              "build", "dist")

# Запись данных. DDL (CREATE/DROP/ALTER) не входит намеренно — см. докстринг.
_DML = re.compile(r"\b(INSERT\s+INTO|INSERT\s+OR\s+\w+\s+INTO|REPLACE\s+INTO"
                  r"|UPDATE\s+[\w\"`\[{]|DELETE\s+FROM)", re.IGNORECASE)

# Методы, которые по HTTP обязаны быть безопасными.
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _writes_data(fn: ast.FunctionDef) -> bool:
    """
    Функция выполняет INSERT / UPDATE / DELETE / REPLACE.

    Ищем в строковых литералах, а не в тексте функции: иначе упоминание
    «исторически здесь был DELETE FROM» в докстринге или закомментированный
    UPDATE делают функцию пишущей. Проверено пробой — так и было.
    Комментарии в AST не попадают вовсе, а докстринги отсеиваются как
    строки-выражения, которые никуда не передаются.
    """
    docstrings = {id(n.value) for n in ast.walk(fn)
                  if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    for node in ast.walk(fn):
        if id(node) in docstrings:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _DML.search(node.value):
                return True
        elif isinstance(node, ast.JoinedStr):
            parts = "".join(v.value for v in node.values
                            if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if _DML.search(parts):
                return True
    return False


def _calls_in(fn: ast.FunctionDef) -> set[str]:
    """Имена, которые функция вызывает. Вложенные def тоже считаются:
    запись из фонового потока вызвана тем же запросом."""
    names = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def _route_methods(fn: ast.FunctionDef) -> set[str] | None:
    """Методы маршрута, или None если функция — не обработчик."""
    for d in fn.decorator_list:
        if not isinstance(d, ast.Call):
            continue
        name = (d.func.attr if isinstance(d.func, ast.Attribute)
                else d.func.id if isinstance(d.func, ast.Name) else "")
        if name != "route":
            continue
        for kw in d.keywords:
            if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                return {e.value.upper() for e in kw.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        return {"GET"}          # methods не указан — Flask слушает GET
    return None


def _collect(roots: list[str]) -> tuple[dict, list, set]:
    """calls: имя → кого зовёт; handlers: безопасные по методу; writers: пишущие."""
    calls, handlers, writers = {}, [], set()

    files = [p for root in roots for p in Path(root).rglob("*.py")
             if not any(part in _SKIP_DIRS for part in p.parts)]

    for path in files:
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            calls.setdefault(fn.name, set()).update(_calls_in(fn))
            if _writes_data(fn):
                writers.add(fn.name)
            methods = _route_methods(fn)
            if methods is not None and methods <= _SAFE_METHODS:
                handlers.append((fn.name, path, fn.lineno, sorted(methods)))

    return calls, handlers, writers


def _path_to_writer(start: str, calls: dict, writers: set) -> list[str] | None:
    """Кратчайшая цепочка вызовов от обработчика до пишущей функции."""
    # Обработчик может писать сам, без промежуточных функций: проверять
    # только вызываемых значило бы пропустить conn.execute("UPDATE ...")
    # прямо в теле маршрута. Найдено пробой при фальсификации.
    if start in writers:
        return [start]
    seen = {start}
    queue = deque([[start]])
    while queue:
        chain = queue.popleft()
        for callee in sorted(calls.get(chain[-1], ())):
            if callee in seen:
                continue
            seen.add(callee)
            if callee in writers:
                return chain + [callee]
            if callee in calls:
                queue.append(chain + [callee])
    return None


def main() -> int:
    roots = sys.argv[1:] or ["."]
    calls, handlers, writers = _collect(roots)

    problems = []
    for name, path, lineno, methods in sorted(handlers, key=lambda h: (str(h[1]), h[2])):
        chain = _path_to_writer(name, calls, writers)
        if chain:
            problems.append(
                f"{path}:{lineno}: {name}() отвечает на {'/'.join(methods)} "
                f"и меняет данные\n      цепочка: " + " → ".join(chain))

    print(f"Безопасных по методу обработчиков: {len(handlers)}")
    print(f"Из них меняют данные: {len(problems)}\n")
    for msg in problems:
        print("  " + msg)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
