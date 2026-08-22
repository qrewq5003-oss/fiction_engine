import ast, sys
from pathlib import Path
for p in sorted(Path(sys.argv[1]).rglob("*.py")):
    if "__pycache__" in str(p): continue
    try: t = ast.parse(p.read_text(encoding="utf-8"), str(p))
    except SyntaxError: continue
    for n in ast.walk(t):
        body = getattr(n, "body", None)
        if not isinstance(body, list): continue
        for i, st in enumerate(body[:-1]):
            if isinstance(st, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                nxt = body[i+1]
                print(f"  {p}:{nxt.lineno} — недостижимо после {type(st).__name__.lower()} (строка {st.lineno})")
