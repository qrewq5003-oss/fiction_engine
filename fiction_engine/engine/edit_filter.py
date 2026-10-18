"""
Фильтр правок судьёй: после круга точечной редактуры судья набора вслепую
сравнивает каждый изменённый фрагмент с исходником; где он выбрал исходник
(или «равно»), правка откатывается.

Замер 18.10 (bench/edit-filter-2026-10-18.json): вторая модель «чужой»
семьи (Opus для правок Sol, Luna для правок Sonnet) считала лучше исходника
81–91 % правок, которые судья оставил бы, и 36–60 % тех, что отбросил бы.
Без фильтра в текст шли и те и другие.

Своё судья не фильтрует: судья той же семьи, что редактор, — фильтра нет.
Ответ судьи не разобран — правки остаются как есть (фильтр не ломает круг).
"""
from __future__ import annotations

import difflib
import random
from typing import Callable

SEP = "\n\n"

SYS_FILTER = "Ты строгий редактор. Отвечай только JSON."

_PROMPT = """Ниже фрагменты главы. У каждого — два варианта, 1 и 2: один исходный,
другой отредактированный, порядок случайный. Для КАЖДОГО фрагмента выбери,
какой вариант лучше как проза в этой книге: точнее, живее, без лишнего,
логичнее. Если разница ничтожна — «равно». Смотри на сам фрагмент и его
контекст, а не на длину.

{items}

Ответь JSON без пояснений вокруг: {{"choices": [{{"n": 1, "better": "1" | "2" | "равно"}}]}}"""


def _opcodes(old: str, new: str) -> tuple[list[str], list[str], list[tuple]]:
    a, b = old.split(SEP), new.split(SEP)
    return a, b, difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()


def filter_edits(old: str, new: str, judge_model: str, editor_model: str,
                 call_fn: Callable[[str, str, str], str], seed: int | None = None) -> tuple[str, dict]:
    """
    → (текст, отчёт). Отчёт: {"checked", "kept", "reverted"} или {"skipped": почему}.
    call_fn(model, system, prompt) — тот же вызов, что у шагов пайплайна.
    """
    from .pipeline_config import model_family
    from .pipeline_llm import parse_json
    if not judge_model:
        return new, {"skipped": "нет судьи"}
    if model_family(judge_model) == model_family(editor_model):
        return new, {"skipped": "судья той же семьи, что редактор"}
    a, b, ops = _opcodes(old, new)
    changed = [op for op in ops if op[0] != "equal"]
    if not changed:
        return new, {"checked": 0, "kept": 0, "reverted": 0}
    rng = random.Random(seed)
    flips = [rng.random() < 0.5 for _ in changed]
    items = []
    for i, ((tag, i1, i2, j1, j2), flip) in enumerate(zip(changed, flips), 1):
        was = SEP.join(a[i1:i2]) or "(абзаца нет)"
        now = SEP.join(b[j1:j2]) or "(абзаца нет)"
        ctx = (a[i1 - 1] if i1 > 0 else "")[-500:]
        v1, v2 = (now, was) if flip else (was, now)
        items.append(f"=== ФРАГМЕНТ {i} ===\nКонтекст перед ним: …{ctx}\n"
                     f"--- Вариант 1 ---\n{v1}\n--- Вариант 2 ---\n{v2}")
    try:
        got = parse_json(call_fn(judge_model, SYS_FILTER, _PROMPT.format(items=SEP.join(items))))
        choices = {int(x.get("n", 0)): str(x.get("better", "")).strip()
                   for x in (got or {}).get("choices", []) if isinstance(x, dict)}
    except Exception:
        choices = {}
    if not choices:
        return new, {"skipped": "ответ судьи не разобран"}
    keep = []
    for i, flip in enumerate(flips, 1):
        v = choices.get(i, "").lower()
        # Нет ответа по фрагменту — правка остаётся: фильтр откатывает только то,
        # что судья явно не выбрал
        keep.append(v == ("1" if flip else "2") or v not in ("1", "2", "равно"))
    out, k = [], 0
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            out += a[i1:i2]
            continue
        out += b[j1:j2] if keep[k] else a[i1:i2]
        k += 1
    kept = sum(keep)
    return SEP.join(out), {"checked": len(changed), "kept": kept, "reverted": len(changed) - kept}
