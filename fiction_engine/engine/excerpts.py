"""
Отрывки прошлых глав для писателя (шаг 3 docs/ENGINE_BOOST.md).

State и L3 — выжимка: они держат сюжет, а не детали. Этаж, шарф, изъятый
плащ меняются и при полном State (замер 12.10). Здесь писатель получает сами
абзацы прошлых глав, где были люди, вещи и места из задачи и плана этой
главы, — как они были написаны.

Без модели: ключи — слова задачи и плана (основы, имена весомее), абзацы
прошлых глав ранжируются по редкости совпавших ключей (idf), лучшие идут в
промпт в пределах бюджета, по порядку глав.
"""

from __future__ import annotations

import math
import re

EXCERPTS_MAX_CHARS = 6000     # весь блок
EXCERPT_PARA_MAX = 700        # один абзац
EXCERPTS_PER_CHAPTER = 12     # на все прошлые главы делится поровну, но не меньше 4 на главу
EXCERPTS_HEADER = "ОТРЫВКИ ПРОШЛЫХ ГЛАВ"

# Включается автором («Настройки → Отрывки прошлых глав») после замера: по
# правилу ENGINE_BOOST блок идёт в движок, только если на двух прогонах
# противоречий меньше. В замере — переменная окружения FE_EXCERPTS=1.
EXCERPTS_SETTING = "excerpts_enabled"


def excerpts_enabled() -> bool:
    import os
    if os.environ.get("FE_EXCERPTS") == "1":
        return True
    try:
        from .db import get_setting
        return (get_setting(EXCERPTS_SETTING) or "") == "1"
    except Exception:          # нет базы — выключено
        return False


_WORD = re.compile(r"[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z\-]{3,}")
# Слова задачи, которые есть почти в любой главе и ничего не находят
_STOP = {
    "глава", "главы", "сцена", "сцены", "задача", "задачи", "тональ", "заканч",
    "который", "которая", "которые", "котор", "потом", "после", "перед", "через",
    "когда", "чтобы", "этого", "этот", "этой", "свой", "своей", "своего", "свою",
    "только", "очень", "может", "можно", "нужно", "будет", "было", "были", "есть",
    "объём", "объем", "слов", "около", "сначала", "затем", "снова", "ещё", "уже",
}


def _stem(word: str) -> str:
    w = word.lower().replace("ё", "е")
    return w if len(w) <= 5 else w[:max(5, len(w) - 2)]


def _keys(focus: str) -> dict[str, float]:
    """Основы слов фокуса → вес: имя (с заглавной не в начале фразы) весомее."""
    keys: dict[str, float] = {}
    for m in _WORD.finditer(focus or ""):
        w = m.group(0)
        s = _stem(w)
        if s in _STOP or len(s) < 4:
            continue
        before = focus[max(0, m.start() - 2):m.start()]
        name = w[0].isupper() and not re.search(r"(^|[.!?:\n]\s*)$", before)
        keys[s] = max(keys.get(s, 0.0), 2.0 if name else 1.0)
    return keys


def _paragraphs(chapters: list[dict]) -> list[tuple[int, int, str]]:
    out = []
    for c in chapters:
        for i, p in enumerate(re.split(r"\n\s*\n", c.get("content") or "")):
            p = p.strip()
            if len(p) >= 40:
                out.append((int(c["number"]), i, p))
    return out


def _trim(p: str) -> str:
    if len(p) <= EXCERPT_PARA_MAX:
        return p
    cut = p[:EXCERPT_PARA_MAX]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("… "))
    return (cut[:end + 1] if end > EXCERPT_PARA_MAX // 2 else cut) + " […]"


def excerpts_block(project_id: int, chapter_num: int, focus_text: str,
                   max_chars: int = EXCERPTS_MAX_CHARS) -> str:
    """Блок «ОТРЫВКИ ПРОШЛЫХ ГЛАВ» для писателя главы chapter_num; «» — нечего дать."""
    if chapter_num <= 1:
        return ""
    keys = _keys(focus_text)
    if not keys:
        return ""
    from .text_signals import previous_chapters
    paras = _paragraphs(previous_chapters(project_id, chapter_num, n=1000))
    if not paras:
        return ""
    stems = [{_stem(w) for w in _WORD.findall(p)} for _, _, p in paras]
    n = len(paras)
    df = {k: sum(1 for s in stems if k in s) for k in keys}
    scored = []
    for (ch, pos, p), s in zip(paras, stems):
        hit = [k for k in keys if k in s]
        if not hit:
            continue
        score = sum(keys[k] * math.log(1 + n / df[k]) for k in hit)
        if ch >= chapter_num - 2:            # свежие главы — чуть важнее
            score *= 1.15
        scored.append((score, ch, pos, p))
    scored.sort(key=lambda x: -x[0])
    picked: list[tuple[int, int, str]] = []
    used, per_ch = 0, {}  # type: int, dict[int, int]
    cap = max(4, EXCERPTS_PER_CHAPTER // len({ch for ch, _, _ in paras}))
    for score, ch, pos, p in scored:
        if per_ch.get(ch, 0) >= cap:
            continue
        t = _trim(p)
        if used + len(t) > max_chars:
            continue
        picked.append((ch, pos, t))
        used += len(t)
        per_ch[ch] = per_ch.get(ch, 0) + 1
    if not picked:
        return ""
    picked.sort()
    body = "\n\n".join(f"[гл.{ch}] {t}" for ch, _, t in picked)
    return (f"{EXCERPTS_HEADER} — так это было написано. Вещи, места, время и приметы "
            f"людей держи ровно так; эти сцены не пересказывай и не повторяй:\n\n{body}")
