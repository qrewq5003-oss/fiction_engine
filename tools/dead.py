import ast, sys
from pathlib import Path
_SKIP_DIRS = ("__pycache__", ".venv", "venv", "site-packages",
              ".mypy_cache", ".pytest_cache", ".hypothesis", ".git", "build", "dist")


def _skip(path) -> bool:
    return any(part in _SKIP_DIRS for part in Path(str(path)).parts)

for p in sorted(Path(sys.argv[1]).rglob("*.py")):
    if _skip(p): continue
    try: t = ast.parse(p.read_text(encoding="utf-8"), str(p))
    except SyntaxError: continue
    for n in ast.walk(t):
        body = getattr(n, "body", None)
        if not isinstance(body, list): continue
        for i, st in enumerate(body[:-1]):
            if isinstance(st, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                nxt = body[i+1]
                print(f"  {p}:{nxt.lineno} — недостижимо после {type(st).__name__.lower()} (строка {st.lineno})")
