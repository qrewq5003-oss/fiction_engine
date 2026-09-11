#!/usr/bin/env python3
"""Скан классических Python-ловушек по AST."""
import ast, sys
from pathlib import Path
ROOT = Path(sys.argv[1])
SKIP_TESTS = "--skip-tests" in sys.argv
found = {}
def add(cat, loc, msg): found.setdefault(cat, []).append((loc, msg))

_SKIP_DIRS = ("__pycache__", ".venv", "venv", "site-packages",
              ".mypy_cache", ".pytest_cache", ".hypothesis", ".git", "build", "dist")


def _skip(path) -> bool:
    return any(part in _SKIP_DIRS for part in Path(str(path)).parts)

for p in sorted(ROOT.rglob("*.py")):
    sp = str(p)
    if _skip(p): continue
    if SKIP_TESTS and ("test" in p.name or "/tests/" in sp): continue
    src = p.read_text(encoding="utf-8")
    try: t = ast.parse(src, sp)
    except SyntaxError: continue
    rel = p.relative_to(ROOT)
    lines = src.splitlines()
    for n in ast.walk(t):
        loc = f"{rel}:{getattr(n,'lineno','?')}"
        # мутабельные значения по умолчанию
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.args.defaults + [x for x in n.args.kw_defaults if x]:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    add("Мутабельный аргумент по умолчанию", loc, f"{n.name}()")
            # голый except
        if isinstance(n, ast.ExceptHandler):
            if n.type is None:
                add("Голый except:", loc, "перехватывает KeyboardInterrupt/SystemExit")
            body = n.body
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                # Широкий перехват с pass — опасный случай: ошибка любого
                # рода превращается в пустой результат. Именно так прожили
                # незамеченными все найденные аудитом функциональные баги.
                #
                # Узкий перехват (json.JSONDecodeError в цепочке разбора,
                # EOFError на Ctrl+D, ImportError для необязательной
                # зависимости) — нормальный приём: ловится ровно то, что
                # ожидается, всё остальное летит дальше. Такие не считаем.
                caught = ast.unparse(n.type) if n.type else "Exception"
                broad = caught in ("Exception", "BaseException") or n.type is None
                if broad:
                    add("широкий except → pass (тихое проглатывание)", loc, caught)
                else:
                    add("узкий except → pass (ожидаемый случай)", loc, caught)
        # is / is not с литералом
        if isinstance(n, ast.Compare):
            for op, cmp in zip(n.ops, n.comparators):
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(cmp, ast.Constant) \
                   and not isinstance(cmp.value, (bool, type(None))):
                    add("`is` с литералом", loc, ast.dump(cmp)[:40])
        # return внутри finally
        if isinstance(n, ast.Try) and n.finalbody:
            for f in n.finalbody:
                for sub in ast.walk(f):
                    if isinstance(sub, ast.Return):
                        add("return в finally", loc, "гасит исключения")
        # open() без encoding
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open":
            kw = {k.arg for k in n.keywords}
            if "encoding" not in kw and not any("b" in (a.value if isinstance(a, ast.Constant) and isinstance(a.value,str) else "") for a in n.args[1:2]):
                add("open() без encoding", loc, "зависит от локали ОС")
        # assert в продуктовом коде
        if isinstance(n, ast.Assert) and "test" not in p.name:
            add("assert в продуктовом коде", loc, "исчезает при python -O")

for cat in sorted(found):
    items = found[cat]
    print(f"\n■ {cat} — {len(items)}")
    for loc, msg in items[:12]:
        print(f"    {loc}  {msg}")
    if len(items) > 12: print(f"    … ещё {len(items)-12}")

# ── Базовая линия ─────────────────────────────────────────────────────────
# Часть находок — исторический долг (40 блоков except → pass). Разгребать их
# разом рискованно, но и копить дальше нельзя. Базовая линия фиксирует
# текущее число: CI падает, только если долг ВЫРОС.
import json
BASELINE = Path(__file__).parent / "pitfalls_baseline.json"
counts = {cat: len(items) for cat, items in found.items()}

if "--update-baseline" in sys.argv:
    BASELINE.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nБазовая линия обновлена: {BASELINE}")
    sys.exit(0)

if "--fail-on-new" in sys.argv:
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    grown = {c: (base.get(c, 0), n) for c, n in counts.items() if n > base.get(c, 0)}
    if grown:
        print("\n✗ Долг вырос по сравнению с базовой линией:")
        for c, (was, now) in sorted(grown.items()):
            print(f"    {c}: было {was}, стало {now}")
        print("\n  Либо исправьте новую находку, либо обновите базу:")
        print("    python tools/pitfalls.py fiction_engine --skip-tests --update-baseline")
        sys.exit(1)
    shrunk = {c: (base[c], counts.get(c, 0)) for c in base if counts.get(c, 0) < base[c]}
    for c, (was, now) in sorted(shrunk.items()):
        print(f"\n✓ {c}: сокращено с {was} до {now} — не забудьте обновить базовую линию")
    print("\n✓ Новых ловушек не добавлено")
sys.exit(0)
