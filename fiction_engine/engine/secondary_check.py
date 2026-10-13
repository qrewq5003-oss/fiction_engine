"""
secondary_check.py — проверка второй линии книги после вердикта судьи.

Судья с оценкой 0–10 и с контрактом второго жанра живую и проваленную линию
не различает (замер 06.10). Различают пять конкретных вопросов о ремесле
линии, 0–2 каждый. Замер 13.10 (bench/ab-secondary-families-2026-10-13.json,
tools/secondary_line/families.py): 7 семейств, по 4 главы в живой и
проваленной версии, писали DeepSeek и Sonnet, судили Kimi, DeepSeek и Sonnet.

Включены семейства, где правило «сумма ≤ 5.5 из 10» по ответу ОДНОГО судьи
ловит проваленную линию и не бракует живую при любом из трёх судей: романтика,
триллер, хоррор (ложный отказ — 1 из 48 живых глав). Фэнтези, детектив, НФ и
реализм — нет: провал там тоньше, и открытые модели его не видят (Sonnet
видит в детективе, фэнтези и НФ). Вопросы для них остались в
tools/secondary_line/families.py, чтобы перемерить на новых моделях.

Вызов один на главу, только у проекта со вторым жанром из включённых
семейств и только если линия в главе есть. Провал — замечание в вердикте и
«НА ДОРАБОТКУ».
"""

from __future__ import annotations

from typing import Callable

FAIL_SUM = 5.5

LINE_QUESTIONS: dict[str, dict] = {
    "romance": {
        "label": "романтическая",
        "Q": ["Чувство показано через детали — что она замечает в нём, паузы, тело, — а не названо "
              "словами («влюблена», «любит»)",
              "Между ними есть напряжение или препятствие, которое мешает прямо сейчас",
              "Признание или влечение подготовлено предыдущими сценами, а не возникает внезапно",
              "Он — живой человек со своими целями и реакциями, а не функция сюжета",
              "Их разговоры несут подтекст: говорят об одном, слышат другое"],
    },
    "thriller": {
        "label": "триллерная",
        "Q": ["Угроза конкретна: известно, кто или что угрожает и чем",
              "Есть ограничение времени или пространства, и оно сжимается",
              "Опасность показана через действия и последствия, а не названа словами",
              "Герой принимает решения под давлением, и эти решения чего-то стоят",
              "Ставка растёт к концу главы или появляется новая угроза"],
    },
    "horror": {
        "label": "хоррор-",
        "Q": ["Страх создаётся деталями восприятия — звук, запах, неправильность, — а не назван "
              "(«ей стало страшно»)",
              "Тревога нарастает постепенно, а не появляется сразу на максимуме",
              "Источник угрозы недосказан: показано достаточно, чтобы тревожить, но не всё объяснено",
              "Реакции героини телесны, она не комментирует собственный страх",
              "Нормальный мир надломлен конкретным, запоминающимся образом, а не общими словами "
              "«мрачно», «зловеще»"],
    },
}

_PROMPT = """Ниже глава книги, где второй жанр — {genre}. Сначала реши, есть ли в этой главе
{label} линия (сцены, где она идёт). Если есть — ответь на вопросы только о ней.
Оценка: 0 — нет, 1 — частично, 2 — да, явно. Сначала короткая цитата-доказательство, потом оценка.

{qs}

=== ГЛАВА ===
{text}

Ответь JSON без пояснений вокруг:
{{"present": "да" или "нет", "answers": [{{"q": 1, "quote": "…", "score": 0}}, …]}}"""


def line_family(secondary_key: str | None) -> str | None:
    """Семейство второго жанра, для которого проверка включена; тон — не жанр."""
    from .genre_mix import MODIFIERS
    if not secondary_key or secondary_key in MODIFIERS:
        return None
    fam = secondary_key.split("_")[0]
    return fam if fam in LINE_QUESTIONS else None


def check_line(text: str, secondary_key: str, genre_label: str,
               call: Callable[[str], str]) -> dict | None:
    """
    None — проверка не нужна или ответ не разобран. Иначе {present, score,
    failed, weak: [вопросы с оценкой 0]}.
    """
    fam = line_family(secondary_key)
    if not fam or not (text or "").strip():
        return None
    q = LINE_QUESTIONS[fam]["Q"]
    from .pipeline_config import CRITIC_TEXT_LIMIT
    from .pipeline_llm import parse_json
    raw = call(_PROMPT.format(genre=genre_label, label=LINE_QUESTIONS[fam]["label"],
                              qs="\n".join(f"{i}. {x}" for i, x in enumerate(q, 1)),
                              text=text[:CRITIC_TEXT_LIMIT]))
    data = parse_json(raw)
    if not isinstance(data, dict):
        return None
    if not str(data.get("present", "")).strip().lower().startswith("да"):
        return {"present": False, "score": None, "failed": False, "weak": []}
    try:
        scores = {int(a["q"]): float(a["score"]) for a in data.get("answers") or []}
    except (KeyError, TypeError, ValueError):
        return None
    if set(scores) != set(range(1, len(q) + 1)):
        return None
    total = sum(scores.values())
    return {"present": True, "score": total, "failed": total <= FAIL_SUM,
            "weak": [q[i - 1] for i, s in sorted(scores.items()) if s == 0]}


def format_line_note(res: dict, genre_label: str) -> str:
    weak = "; ".join(res["weak"][:3]) or "оценки низкие по всем вопросам"
    return (f"ВТОРАЯ ЛИНИЯ ({genre_label}) провалена: {res['score']:g} из 10. Не выполнено: {weak}. "
            f"Перепиши сцены этой линии — показывать, а не называть.")
