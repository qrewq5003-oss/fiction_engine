"""
Точечная редактура по критике — круг «Ещё круг редактуры» без переписывания.

Прежний редактор получал «перепиши текст, исправив все проблемы» и
возвращал главу заново. На главах автора 17.10 круг менял 14–59 % слов,
глава 2 за два круга потеряла 40 % объёма, а «Кратохвил», «одиннадцать в
подвале» и «под обезболом» появились именно на кругах редактуры — в местах,
о которых критика молчала.

Здесь редактор возвращает список правок: «фрагмент дословно → чем
заменить» и «вставить после фрагмента». Подставляет их код (тем же поиском,
что у правщика непрерывности, `continuity_fix`); всё остальное остаётся
слово в слово.
"""
from __future__ import annotations

import re
from typing import Callable

EDIT_MODE_KEY = "edit_mode"
EDIT_MODES = ("points", "rewrite")   # точечно — по умолчанию; целиком — по выбору автора
POINT_EDITS_MAX = 15
INSERT_WORDS_MAX = 600

SYS_POINT_EDITOR = ("Ты — редактор и автор этой книги. Правишь главу точечно по критике: "
                    "только названные места. Отвечаешь только JSON.")

_PROMPT = """Ниже задача главы, критика и сама глава. Исправь проблемы, которые
называет критика, ТОЧЕЧНО — главу не переписывай.

Правки двух видов:
- замена: "old" — фрагмент главы дословно (одно–три предложения, чтобы найти
  его однозначно), "new" — тот же фрагмент, исправленный;
- вставка: "after" — фрагмент главы дословно, после абзаца с которым вставить,
  "new" — новый текст (абзац или сцена, до {insert_max} слов). Вставка — для
  того, чего в главе нет, а задача или критика требует.

Правила:
- Не трогай места, о которых критика молчит.
- Имена, факты, время, места и кто что знает — как в главе и в задаче; новых
  фактов о прошлом не вводи.
- Сохраняй голос, ритм и длину абзацев главы.
- Совет критика, с которым текст лучше не станет, можно пропустить.
- Не больше {max_edits} правок; важные — первыми.

=== ЗАДАЧА ГЛАВЫ ===
{task}

=== КРИТИКА ===
{critique}

=== ГЛАВА ===
{text}

Ответь JSON без пояснений вокруг:
{{"edits": [{{"old": "…", "new": "…", "why": "…"}}, {{"after": "…", "new": "…", "why": "…"}}]}}"""


def edit_mode() -> str:
    """Режим «Ещё круга редактуры» из настроек: points (точечно) или rewrite."""
    try:
        from .db_settings import get_setting
        m = (get_setting(EDIT_MODE_KEY) or "").strip()
    except Exception:          # нет базы — по умолчанию
        m = ""
    return m if m in EDIT_MODES else "points"


def _locate(text: str, fragment: str) -> tuple[int, int] | None:
    """Где в тексте фрагмент: дословно → по словам → по первому и последнему предложению."""
    from .continuity_fix import _anchored_span, _flex_pattern
    if fragment and fragment in text:
        i = text.index(fragment)
        return i, i + len(fragment)
    pat = _flex_pattern(fragment)
    m = pat.search(text) if pat else None
    if m:
        return m.start(), m.end()
    return _anchored_span(text, fragment)


def _insert_after(text: str, after: str, new: str) -> str | None:
    """Вставить new отдельным абзацем после абзаца, где стоит after; не нашёлся — None."""
    span = _locate(text, after)
    if not span:
        return None
    end = text.find("\n\n", span[1])
    end = len(text) if end < 0 else end
    return text[:end].rstrip() + "\n\n" + new.strip() + "\n\n" + text[end:].lstrip("\n")


def point_edit(text: str, critique: str, task: str, api_call_fn: Callable[[str], str]) -> dict:
    """
    → {text, applied, failed, changed}. Модель не дала правок или ответ не
    разобран — текст как был (failed объясняет почему).
    """
    from .continuity_fix import apply_edits, changed_share
    from .pipeline_llm import parse_json
    raw = api_call_fn(_PROMPT.format(task=(task or "").strip() or "—", critique=critique.strip(),
                                     text=text, max_edits=POINT_EDITS_MAX,
                                     insert_max=INSERT_WORDS_MAX))
    try:
        data = parse_json(raw)
    except Exception:
        data = None
    edits = data if isinstance(data, list) else data.get("edits") if isinstance(data, dict) else None
    if not isinstance(edits, list):
        return {"text": text, "applied": [], "failed": [{"why": "ответ редактора не разобран"}],
                "changed": 0.0}
    edits = [e for e in edits if isinstance(e, dict)][:POINT_EDITS_MAX]
    replaces = [e for e in edits if not e.get("after")]
    inserts = [e for e in edits if e.get("after")]
    out, applied, failed = apply_edits(text, replaces)
    for e in inserts:
        new = str(e.get("new") or "").strip()
        if not new:
            failed.append(dict(e, why="пустая вставка"))
            continue
        if len(new.split()) > INSERT_WORDS_MAX:
            new = " ".join(new.split()[:INSERT_WORDS_MAX])
            new = new[:new.rfind(".") + 1] or new
        got = _insert_after(out, str(e["after"]), new)
        if got is None:
            failed.append(dict(e, why="место вставки не найдено в главе"))
        else:
            out = got
            applied.append(dict(e, way="insert"))
    out = re.sub(r"\n{3,}", "\n\n", out)
    return {"text": out, "applied": applied, "failed": failed,
            "changed": round(changed_share(text, out), 3)}
