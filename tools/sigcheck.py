#!/usr/bin/env python3
"""Кросс-модульная проверка сигнатур вызовов (arity + имена kwargs)."""
import ast, sys
from pathlib import Path

ROOT = Path(sys.argv[1])
_SKIP_DIRS = ("__pycache__", ".venv", "venv", "site-packages",
              ".mypy_cache", ".pytest_cache", ".hypothesis", ".git", "build", "dist")


def _skip(path) -> bool:
    return any(part in _SKIP_DIRS for part in Path(str(path)).parts)

files = [p for p in ROOT.rglob("*.py") if not _skip(p)]

def modname(p):
    rel = p.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__": parts = parts[:-1]
    return ".".join(parts)

# ── 1. Сигнатуры всех функций/методов ────────────────────────────────
sigs = {}   # (module, qualname) -> info
trees = {}
for p in files:
    try: t = ast.parse(p.read_text(encoding="utf-8"), str(p))
    except SyntaxError as e:
        print(f"SYNTAX ERROR {p}: {e}"); continue
    trees[p] = t
    m = modname(p)
    for node in ast.walk(t):
        # Классы: конструктор по __init__, а для dataclass — по полям.
        # Без этого дрейф сигнатур в ClassName(...) проходил незамеченным:
        # именно так проскочили ChapterAnalyzer(save_gaps_fn=...),
        # NarrativeReport(...) и PromiseItem(chapter=...).
        if isinstance(node, ast.ClassDef):
            init = next((b for b in node.body
                         if isinstance(b, ast.FunctionDef) and b.name == "__init__"), None)
            is_dc = any(("dataclass" in ast.dump(d)) for d in node.decorator_list)
            if init is not None:
                a = init.args
                pos = [x.arg for x in a.posonlyargs + a.args][1:]   # без self
                sigs.setdefault((m, node.name), dict(
                    pos=pos, ndef=len(a.defaults),
                    vararg=a.vararg is not None, kwarg=a.kwarg is not None,
                    kwonly=[x.arg for x in a.kwonlyargs],
                    kwonly_req=[x.arg for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is None],
                    line=node.lineno, module=m, decorated=False, is_class=True,
                ))
            elif is_dc:
                fields, defaults = [], 0
                for b in node.body:
                    if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name):
                        fields.append(b.target.id)
                        if b.value is not None:
                            defaults += 1
                sigs.setdefault((m, node.name), dict(
                    pos=fields, ndef=defaults, vararg=False, kwarg=False,
                    kwonly=[], kwonly_req=[], line=node.lineno, module=m,
                    decorated=False, is_class=True,
                ))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            pos = [x.arg for x in a.posonlyargs + a.args]
            info = dict(
                pos=pos, ndef=len(a.defaults),
                vararg=a.vararg is not None, kwarg=a.kwarg is not None,
                kwonly=[x.arg for x in a.kwonlyargs],
                kwonly_req=[x.arg for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is None],
                line=node.lineno, module=m, decorated=bool(node.decorator_list),
                is_class=False,
            )
            sigs.setdefault((m, node.name), info)

# ── 2. Разбор вызовов ────────────────────────────────────────────────
problems = []
for p, t in trees.items():
    m = modname(p)
    # локальные алиасы: имя -> (модуль, функция)
    alias = {}
    for node in ast.walk(t):
        if isinstance(node, ast.ImportFrom) and node.module:
            base = node.module
            if node.level:                      # relative import
                pkg = m.rsplit(".", 1)[0] if "." in m else m
                base = f"{pkg}.{node.module}" if node.module else pkg
            for n in node.names:
                alias[n.asname or n.name] = (base, n.name)
    # методы класса пропускаем (self), считаем только свободные функции
    for node in ast.walk(t):
        if not isinstance(node, ast.Call): continue
        fn = node.func
        key = None
        if isinstance(fn, ast.Name) and fn.id in alias:
            mod, name = alias[fn.id]
            key = (mod, name)
        elif isinstance(fn, ast.Name):
            key = (m, fn.id)
        if key is None or key not in sigs: continue
        s = sigs[key]
        if s["decorated"]: pass          # декораторы могут менять сигнатуру, но чаще нет
        npos = len([a for a in node.args if not isinstance(a, ast.Starred)])
        has_star = any(isinstance(a, ast.Starred) for a in node.args)
        kwnames = [k.arg for k in node.keywords if k.arg]
        has_dstar = any(k.arg is None for k in node.keywords)
        if has_star or has_dstar: continue
        pos = s["pos"]
        # пропускаем методы (первый арг self/cls) — но не конструкторы классов,
        # у которых self уже отрезан при сборе
        if not s.get("is_class") and pos and pos[0] in ("self", "cls"): continue
        minreq = len(pos) - s["ndef"]
        supplied = set(pos[:npos]) | set(kwnames)
        loc = f"{p.relative_to(ROOT)}:{node.lineno}"
        tgt = f"{key[0]}.{key[1]}()"
        if npos > len(pos) and not s["vararg"]:
            problems.append((loc, tgt, f"слишком много позиционных: {npos} > {len(pos)}"))
            continue
        missing = [a for a in pos[:minreq] if a not in supplied]
        if missing:
            problems.append((loc, tgt, f"не передан обязательный аргумент: {', '.join(missing)}"))
        unknown = [k for k in kwnames if k not in pos and k not in s["kwonly"] and not s["kwarg"]]
        if unknown:
            problems.append((loc, tgt, f"неизвестный kwarg: {', '.join(unknown)}"))
        missing_kw = [k for k in s["kwonly_req"] if k not in kwnames]
        if missing_kw:
            problems.append((loc, tgt, f"не передан kw-only: {', '.join(missing_kw)}"))

uniq = sorted(set(problems))
print(f"Проверено файлов: {len(trees)}, известных функций: {len(sigs)}")
print(f"Найдено расхождений: {len(uniq)}\n")
for loc, tgt, msg in uniq:
    print(f"  {loc}\n      {tgt} — {msg}")

sys.exit(1 if uniq else 0)
