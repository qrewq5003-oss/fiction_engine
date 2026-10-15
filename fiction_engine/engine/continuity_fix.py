"""
Точечная правка главы по находкам проверки непрерывности.

Проверка (`continuity_checker.check_against_chapters`) даёт пары цитат:
quote_a из прошлой главы, quote_b из новой, и что именно разошлось. Здесь
писатель получает эти пары и возвращает список замен «старый фрагмент →
новый»; фрагменты подставляются в текст по точному совпадению. Главу целиком
модель не переписывает: иначе меняется и то, что менять не просили.

Прошлая глава — истина: правится всегда новая. Если по тексту это не ошибка
(ложь персонажа, развитие), модель вправе не давать замену.
"""
import json
import re
from typing import Callable

LLMCaller = Callable[[str], str]

_CTX_RADIUS = 300             # символов вокруг цитаты прошлой главы — чтобы было видно, как было

_FIX_PROMPT = """Ниже глава {num} серии и список мест, где она противоречит прошлым главам.
Прошлые главы — истина; править нужно главу {num}, и только в этих местах.

Для каждого противоречия найди в главе {num} ВСЕ фрагменты, где звучит неверный
факт (не только процитированный), и дай замену: «old» — фрагмент дословно, как
в главе (одно-три предложения, достаточно, чтобы найти его однозначно), «new» —
тот же фрагмент, согласованный с прошлой главой. Сохраняй голос, ритм, объём и
всё, что не касается противоречия. Если текст подаёт расхождение как ложь или
догадку персонажа и это видно читателю — замену не давай.

=== ПРОТИВОРЕЧИЯ ===
{items}

=== ГЛАВА {num} ===
{text}

Ответь JSON без пояснений вокруг:
{{"edits": [{{"old": "…", "new": "…"}}]}}"""


def _flex_pattern(fragment: str, min_words: int = 2) -> re.Pattern | None:
    """
    Регулярка по словам фрагмента: между словами — любые пробелы и знаки,
    ё = е, регистр не важен. Модель, цитируя главу, меняет кавычки, тире и
    запятые чаще, чем слова; по словам фрагмент из нескольких слов однозначен.
    """
    words = re.findall(r"\w+", fragment or "")
    if len(words) < min_words:
        return None
    parts = [re.escape(w).replace("ё", "е").replace("Ё", "Е").replace("е", "[её]").replace("Е", "[ЕЁ]")
             for w in words]
    f = (fragment or "").strip()
    # Края: открывающая кавычка и знаки после последнего слова входят в замену,
    # иначе после подстановки остаются «««» и «..»
    head = r"[«\"„“]?\s*" if re.match(r"[«\"„“]", f) else ""
    tail = r"[^\w\s]*" if re.search(r"[^\w\s]$", f) else ""
    return re.compile(head + r"[\W_]*".join(parts) + tail, re.IGNORECASE)


def _anchored_span(text: str, old: str) -> tuple[int, int] | None:
    """
    Фрагмент целиком не нашёлся (середину модель пересказала) — ищем по
    первому и последнему предложению; между ними не больше двух длин фрагмента.
    """
    sents = [s for s in re.split(r"(?<=[.!?…»])\s+", old.strip()) if s]
    nw = lambda s: len(re.findall(r"\w+", s))
    head: list[str] = []
    i = 0
    while i < len(sents) and nw(" ".join(head)) < 3:      # край — от 3 слов, чтобы был однозначен
        head.append(sents[i]); i += 1
    tail: list[str] = []
    j = len(sents)
    while j > i and nw(" ".join(tail)) < 3:
        j -= 1; tail.insert(0, sents[j])
    if nw(" ".join(head)) < 3 or nw(" ".join(tail)) < 3:
        return None
    p1, p2 = _flex_pattern(" ".join(head), 3), _flex_pattern(" ".join(tail), 3)
    m1 = p1.search(text) if p1 else None
    m2 = p2.search(text, m1.end()) if (m1 and p2) else None
    if not m1 or not m2 or m2.end() - m1.start() > 2 * len(old) + 80:
        return None
    return m1.start(), m2.end()


def quote_context(text: str, quote: str, radius: int = _CTX_RADIUS) -> str:
    """Окно текста вокруг цитаты; цитата не нашлась — пусто."""
    pat = _flex_pattern(quote)
    m = pat.search(text or "") if pat else None
    if not m:
        return ""
    return text[max(0, m.start() - radius):m.end() + radius].strip()


def apply_edits(text: str, edits: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """
    Подставить замены: точное совпадение → по словам → по первому и последнему
    предложению. Возвращает (текст, применённые, не применённые); у применённых
    поле way (exact | words | anchored), у остальных why — не найдено в главе
    или перекрыто другой заменой.
    """
    original = text
    applied, failed = [], []
    for e in edits:
        old, new = str(e.get("old") or ""), str(e.get("new") or "")
        if not old.strip() or old == new:
            failed.append(dict(e, why="пустая замена"))
            continue
        pat = _flex_pattern(old)
        if old in text:
            span, way = (text.index(old), text.index(old) + len(old)), "exact"
        elif pat and (m := pat.search(text)):
            span, way = (m.start(), m.end()), "words"
        elif (sp := _anchored_span(text, old)):
            span, way = sp, "anchored"
        else:
            seen = bool(pat and pat.search(original)) or old in original
            failed.append(dict(e, why="перекрыто другой заменой" if seen else "не найдено в главе"))
            continue
        text = text[:span[0]] + new + text[span[1]:]
        applied.append(dict(e, way=way))
    return text, applied, failed


def fix_contradictions(chapter_num: int, text: str, found: list[dict],
                       previous: list[dict], api_call_fn: LLMCaller) -> dict:
    """
    Правка главы по находкам проверки. found — [{chapter_a, quote_a, quote_b, what}],
    previous — [{number, content}]. Возвращает {text, edits, applied, failed}.
    Без находок — текст как есть, вызова нет.
    """
    if not found or not (text or "").strip():
        return {"text": text, "edits": [], "applied": [], "failed": []}
    by_num = {p["number"]: p.get("content") or "" for p in previous}
    lines = []
    for i, f in enumerate(found, 1):
        ctx = quote_context(by_num.get(f["chapter_a"], ""), f["quote_a"])
        lines.append(f"{i}. {f['what']}\n   Глава {f['chapter_a']}: «{f['quote_a']}»"
                     + (f"\n   Как это было в главе {f['chapter_a']}: …{ctx}…" if ctx else "")
                     + f"\n   Глава {chapter_num}: «{f['quote_b']}»")
    raw = api_call_fn(_FIX_PROMPT.format(num=chapter_num, items="\n".join(lines), text=text))
    from .pipeline_llm import parse_json
    data = parse_json(raw)
    edits = data.get("edits") if isinstance(data, dict) else data
    if not isinstance(edits, list):
        raise ValueError("правка непрерывности: ответ модели не разобран")
    edits = [e for e in edits if isinstance(e, dict)]
    new_text, applied, failed = apply_edits(text, edits)
    return {"text": new_text, "edits": edits, "applied": applied, "failed": failed}


def edits_summary(result: dict) -> str:
    """Короткая строка для лога: сколько замен применено и сколько не нашлось."""
    return f"замен {len(result['applied'])} из {len(result['edits'])}" + \
        (f", не найдено {len(result['failed'])}" if result["failed"] else "")


def changed_share(before: str, after: str) -> float:
    """Доля изменённых слов (0–1) — чтобы видеть, не переписала ли модель лишнего."""
    import difflib
    a, b = before.split(), after.split()
    if not a:
        return 0.0
    same = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False)
               .get_matching_blocks())
    return round(1 - same / max(len(a), len(b)), 4)


__all__ = ["fix_contradictions", "apply_edits", "quote_context", "edits_summary",
           "changed_share"]
