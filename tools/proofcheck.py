#!/usr/bin/env python3
"""
proofcheck.py — доказательства должны проверять то, что собирают.

Повод. Список исключений из класс-теста был прозой: «маршрут безопасен,
потому что…». Одна запись оказалась ложной, маршрут вышел из-под проб и
утекал чужие данные при зелёном тесте. Прозу заменили исполняемыми
доказательствами — и та же ошибка воспроизвелась внутри функции:

    opened = []
    sqlite3.connect = lambda *a, **kw: (opened.append(a[0]), real(*a, **kw))[1]
    client.post(...)
    assert get_scene(...)["title"] == "ЧУЖАЯ-2"    # проверяет НЕ opened

Докстринг обещал «обработчик не обращается к базе», а проверялось, что
чужая сцена не изменена — она и не могла, обработчик ничего не пишет.
Наблюдение собрали и выбросили. Ложное обоснование просто переехало из
строки списка в докстринг функции.

Правило. В теле доказательства каждый НАКОПИТЕЛЬ — имя, которому
присвоен пустой список, словарь или множество, — обязан появиться хотя
бы в одном `assert`. Накопитель заводят ради наблюдения; если его не
проверяют, доказательство утверждает не то, что делает.

Правило намеренно узкое: `real = sqlite3.connect` накопителем не
считается и ложных срабатываний не даёт.

Запуск:
    python3 tools/proofcheck.py fiction_engine planner
"""

import ast
import sys
from pathlib import Path

_SKIP_DIRS = ("__pycache__", ".venv", "venv", "site-packages",
              ".mypy_cache", ".pytest_cache", ".git")

_EMPTY_CONTAINERS = (ast.List, ast.Dict, ast.Set)

# Заводские способы завести пустой накопитель
_COLLECTOR_FACTORIES = ("list", "dict", "set", "Counter", "defaultdict", "deque")


def _is_collector(node: ast.AST) -> bool:
    """
    Накопитель — то, что заводят пустым, чтобы наполнить наблюдением.

    Три вида:
      контейнер-литерал   x = [] / {} / set()
      фабрика             x = list() / Counter() / defaultdict(...) / deque()
      флаг или счётчик    x = False / x = 0

    Флаг добавлен по разбору: тот же дефект пишется не только списком —

        touched = False
        def spy(*a, **kw):
            nonlocal touched; touched = True; return real(*a, **kw)
        ...
        assert get_scene(...) is not None      # touched не проверен

    и узкое правило пропускало его целиком.

    Обычные присваивания вроде `real = sqlite3.connect` накопителями не
    считаются: это Attribute, а не пустой контейнер и не флаг.
    """
    if isinstance(node, _EMPTY_CONTAINERS):
        return not getattr(node, "elts", None) and not getattr(node, "keys", None)
    if isinstance(node, ast.Call):
        name = (node.func.id if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute)
                else "")
        if name == "defaultdict":
            return True          # аргумент — фабрика значений, сам он пуст
        # Остальные фабрики считаются накопителем только без аргументов:
        # `set(re.findall(...))` — это готовый результат, а не наблюдение,
        # которое собираются наполнять.
        return name in _COLLECTOR_FACTORIES and not node.args and not node.keywords
    # Флаг наблюдения или счётчик, заведённый «пустым»
    return isinstance(node, ast.Constant) and node.value in (False, 0) \
        and not isinstance(node.value, str)


def _names_in_asserts(fn: ast.AST) -> set[str]:
    names = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Assert):
            names |= {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}
    return names


def check_file(path: Path) -> list[str]:
    problems = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or not fn.name.startswith("_proof_"):
            continue
        asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
        asserted = _names_in_asserts(fn)
        if not asserts:
            problems.append(
                f"{path}:{fn.lineno}: {fn.name}() не содержит ни одного assert")
            continue
        if not asserted:
            # Assert есть, но проверяет константы: `assert 2 + 2 == 4`.
            # Прежнее сообщение утверждало, что assert отсутствует, —
            # и уводило от причины. Инструмент как раз о том, что
            # заявление обязано совпадать с проверкой.
            problems.append(
                f"{path}:{fn.lineno}: {fn.name}() — ни один assert "
                "не проверяет переменных")
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and _is_collector(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in asserted:
                        problems.append(
                            f"{path}:{node.lineno}: {fn.name}() собирает "
                            f"{target.id!r}, но нигде его не проверяет")
    return problems


def main() -> int:
    roots = sys.argv[1:] or ["."]
    files = [p for root in roots for p in Path(root).rglob("test_*.py")
             if not any(part in _SKIP_DIRS for part in p.parts)]
    problems = [msg for f in files for msg in check_file(f)]

    print(f"Проверено файлов: {len(files)}")
    print(f"Доказательств с разрывом «собрал — не проверил»: {len(problems)}\n")
    for msg in problems:
        print("  " + msg)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
