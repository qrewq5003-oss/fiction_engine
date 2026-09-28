"""
foreign_words.py — английские вставки в русской прозе.

Зачем. Генератор посреди русской фразы переходит на английский:
«kissed her», «laid off tonight», «footsteps», однажды — «outputPath».
Проверка 28.09 по главам A/B-замеров: 21 из 32 глав GLM-5.3 с такими
вставками. Судьи их почти не замечают (оценка «чистоты» у всех жанров
около 6.8, вставки в замечаниях не всплывают), а читатель спотыкается
сразу.

Как лечится. Не переписыванием главы — редактура уже замерялась и
срезала четверть объёма (pipeline_config, профиль DEEP). Модели уходят
только предложения со вставками, назад — те же предложения по-русски.
Замена принимается, только если в ней не осталось латиницы и длина
почти та же; иначе остаётся исходное предложение. Поиск и подстановка —
арифметика, модель лишь переводит.

Что вставкой не считается:
- римские числа (глава XIV);
- одиночная латинская буква («план B»);
- слово, которое уже есть в промпте главы: если автор сам пишет «Wi-Fi»
  или назвал корабль «Nostromo», это его выбор, а не сбой модели.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# Слово целиком: кириллица, латиница, дефис и апостроф внутри. Вставка —
# слово, в котором есть хоть одна латинская буква: ловит и «footsteps»,
# и смешанное «мaма» с латинской «a».
_WORD = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:['’-][A-Za-zА-Яа-яЁё]+)*")
_LATIN = re.compile(r"[A-Za-z]")
_ROMAN = re.compile(r"^[IVXLCDM]+$")

# Граница предложения: знак конца фразы (с закрывающей кавычкой), после
# которого пробел или конец текста, — или перевод строки. Точка без
# пробела границей не считается: модель пишет и «под.controlем», и если
# отрезать фразу по этой точке, корректор получит обрубок «controlем весь
# разговор» и переведёт его наугад («Управляла весь разговор»).
_SENTENCE_END = re.compile(r"[.!?…]+[»”\"')]*(?=\s|$)|\n")

# Замена не должна менять длину сильнее этого: перевод пары слов
# не превращает фразу в абзац и не сжимает её вдвое.
_LEN_RATIO = (0.7, 1.5)

MAX_SENTENCES = 40   # больше — глава испорчена целиком, чинить по фразам нельзя


def foreign_words(text: str, allowed: str = "") -> list[str]:
    """Английские вставки в тексте, по порядку, без повторов."""
    allowed_words = {w.lower() for w in _WORD.findall(allowed or "")}
    seen: dict[str, None] = {}
    for w in _WORD.findall(text or ""):
        if not _LATIN.search(w) or w.lower() in allowed_words:
            continue
        if _ROMAN.match(w) or (len(w) == 1 and w.isascii()):
            continue
        seen.setdefault(w, None)
    return list(seen)


def _sentence_span(text: str, pos: int) -> tuple[int, int]:
    """Границы предложения, в котором стоит символ pos."""
    # Ищем по всему тексту, а не в text[:pos]: при endpos=pos проверка
    # «после точки пробел или конец» принимала pos за конец текста, и
    # «под.controlем» снова резалось по точке.
    start = 0
    for m in _SENTENCE_END.finditer(text):
        if m.end() > pos:
            break
        start = m.end()
    m = _SENTENCE_END.search(text, pos)
    end = m.end() if m else len(text)
    # Пробелы по краям не входят в предложение — подстановка их не трогает
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def sentences_with_foreign(text: str, allowed: str = "") -> list[tuple[int, int]]:
    """Отрезки предложений со вставками, по порядку, без пересечений."""
    bad = set(foreign_words(text, allowed))
    if not bad:
        return []
    spans: list[tuple[int, int]] = []
    for m in _WORD.finditer(text):
        if m.group() not in bad:
            continue
        span = _sentence_span(text, m.start())
        if not spans or span[0] >= spans[-1][1]:
            spans.append(span)
    return spans


FIX_SYSTEM = ("Ты корректор русской художественной прозы. Отвечаешь только JSON.")

FIX_PROMPT = """В этих предложениях из русской главы по ошибке оказались английские слова.
Замени каждое английское слово русским по смыслу и по контексту фразы.
Если английское слово склеено с русским («controlем», «СегодняLate») или
отделено от соседнего лишней точкой («под.controlем»), исправь и склейку.
Всё остальное оставь как есть: слова, порядок, пунктуацию. Не улучшай стиль.
Имя или название, написанное латиницей, передай кириллицей.

{items}

Ответь JSON: {{"1": "исправленное предложение", "2": "…"}} — для каждого номера."""

# Модель недетерминирована: на проверке 28.09 примерно каждый третий
# ответ GLM-5.3 возвращал фразу с той же латиницей («clothовые повязки»)
# или вовсе без правки. Следующий проход берёт только то, что осталось, —
# в том числе когда прошлый не исправил ничего: именно тогда повтор нужнее.
FIX_PASSES = 3

# Запас на рассуждение: GLM-5.3 сначала думает, и при потолке 1000 токенов
# думание съедало весь ответ — finish_reason=length, пустая строка, глава
# с тремя вставками осталась нетронутой. Потолок не предоплата: платится
# только выданное.
FIX_MAX_TOKENS = 4000


def _fix_pass(text: str, model_value: str, call_fn: Callable[..., str],
              allowed: str) -> tuple[str, list[str]]:
    """Один проход: все предложения со вставками — одним вызовом."""
    from .error_policy import ErrorLevel, handle_error

    spans = sentences_with_foreign(text, allowed)
    if not spans or len(spans) > MAX_SENTENCES:
        return text, []
    originals = [text[a:b] for a, b in spans]
    items = "\n".join(f"{i}. {s}" for i, s in enumerate(originals, 1))
    try:
        raw = call_fn(model_value, FIX_SYSTEM, FIX_PROMPT.format(items=items),
                      max_tokens=FIX_MAX_TOKENS + sum(len(s) for s in originals))
        from .pipeline_llm import parse_json
        answer = parse_json(raw or "") or {}
    except Exception as e:
        handle_error("fix_foreign_words", e, level=ErrorLevel.RECOVERABLE)
        return text, []
    if not isinstance(answer, dict):
        return text, []
    fixed_words: list[str] = []
    out = text
    for i in range(len(spans), 0, -1):          # с конца — смещения не плывут
        a, b = spans[i - 1]
        old, new = originals[i - 1], answer.get(str(i))
        if not isinstance(new, str) or not new.strip():
            continue
        new = new.strip()
        ratio = len(new) / max(1, len(old))
        if foreign_words(new, allowed) or not _LEN_RATIO[0] <= ratio <= _LEN_RATIO[1]:
            continue
        fixed_words = foreign_words(old, allowed) + fixed_words
        out = out[:a] + new + out[b:]
    return out, fixed_words


def fix_foreign_words(text: str, model_value: str, call_fn: Callable[..., str],
                      allowed: str = "") -> tuple[str, list[str]]:
    """
    Заменить английские вставки по-русски, трогая только их предложения.

    Возвращает (текст, исправленные слова). Ошибка вызова или разбора —
    текст остаётся как был: вставка хуже перевода, но лучше потерянной главы.
    """
    fixed: list[str] = []
    for _ in range(FIX_PASSES):
        if not foreign_words(text, allowed):
            break
        text, words = _fix_pass(text, model_value, call_fn, allowed)
        fixed += words
    return text, fixed
