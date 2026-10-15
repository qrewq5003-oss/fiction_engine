"""
timeline.py — проверка времени в плане без модели.

Поле «время» сцены — свободный текст: «утро понедельника», «вторник, 18:40»,
«12 октября, ночь», «на следующий день». Отсюда берутся день недели, дата,
часы или часть суток и пометки «на следующий день» / «через три дня». Сцены
идут в порядке доски (акты по порядку, внутри — по позиции), и проверяется:

- день недели после предыдущего отстоит на 4–6 дней — скорее всего, день
  перепутан (четверг → вторник); «через», «неделя» в тексте снимают вопрос;
- «на следующий день», а день недели не следующий;
- дата раньше предыдущей;
- дата и день недели расходятся с предыдущей сценой (12-е — вторник, 14-е — пятница);
- в тот же день — явно тот же: тот же день недели или та же дата — время
  раньше, чем в предыдущей сцене.

Без явного дня порядок времени суток не проверяется: «вечер», потом «утро» —
обычно уже следующий день. Флешбэк, воспоминание, «за год до» — сцена
пропускается и состояние не меняет.

Это подсказки автору, а не ошибки: план отправляется как есть.
"""

from __future__ import annotations

import re

_WEEKDAYS = [
    r"понедельник\w*|\bпн\b", r"вторник\w*|\bвт\b", r"сред[аеуы]\b|\bср\b",
    r"четверг\w*|\bчт\b", r"пятниц\w*|\bпт\b", r"суббот\w*|\bсб\b",
    r"воскресень\w*|\bвс\b",
]
_WD_NAMES = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_MONTHS = ["январ", "феврал", "март", "апрел", "ма[йя]", "июн", "июл", "август",
           "сентябр", "октябр", "ноябр", "декабр"]
_MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
# Часть суток → минуты от полуночи, чтобы сравнивать с часами
_PARTS = [
    (r"рассвет|\bутр\w*|наутро", 8 * 60),
    (r"полдень|полдн\w*|\bобед\w*|\bдн[её]м\b|\bдень\b|\bдня\b", 13 * 60),
    (r"сумерк\w*|\bвечер\w*", 19 * 60),
    (r"полноч\w*|\bноч\w*", 23 * 60),
]
_NEXT_DAY = re.compile(r"следующ\w* (?:день|утр\w*|вечер\w*|ноч\w*)|назавтра|наутро|на другой день")
_GAP = re.compile(r"\bчерез\b|недел")
_FLASHBACK = re.compile(r"флешб[еэ]к|воспоминани|в прошлом|\bранее\b|\bдо (?:этого|того)\b|"
                        r"\bза \w+ (?:до|раньше)\b|(?:год|месяц|недел\w*) (?:назад|раньше)")


def parse(text: str) -> dict:
    """День недели (0–6), дата (месяц, число), минуты, пометки. Чего нет — None."""
    t = (text or "").lower().replace("ё", "е")
    out: dict = {"weekday": None, "date": None, "minutes": None,
                 "next_day": bool(_NEXT_DAY.search(t)), "gap": bool(_GAP.search(t)),
                 "flashback": bool(_FLASHBACK.search(t))}
    for i, pat in enumerate(_WEEKDAYS):
        if re.search(pat, t):
            out["weekday"] = i
            break
    m = re.search(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\w*", t)
    if m:
        month = next(i for i, p in enumerate(_MONTHS) if re.match(p, m.group(2)))
        out["date"] = (month + 1, int(m.group(1)))
    else:
        m = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.\d{2,4})?\b", t)
        if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31:
            out["date"] = (int(m.group(2)), int(m.group(1)))
    # «на следующий день» — про день, а не про время суток
    t = re.sub(r"(?:следующ\w*|другой) день", " ", t)
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
    if m:
        out["minutes"] = int(m.group(1)) * 60 + int(m.group(2))
    else:
        for pat, minutes in _PARTS:
            if re.search(pat, t):
                out["minutes"] = minutes
                break
    return out


def _day_of_year(date: tuple[int, int]) -> int:
    month, day = date
    return sum(_MONTH_DAYS[:month - 1]) + day


def _ddmm(d: tuple[int, int]) -> str:
    return f"{d[1]:02d}.{d[0]:02d}"


def check(scenes: list[dict]) -> list[dict]:
    """
    scenes — в порядке плана, у каждой title и time_of_day (и id, если есть).
    Возвращает [{scene_id, title, message}] — по сцене, где замечено.

    День сравнивается с последним явно названным (сцены без дня между ними
    его не сдвигают и не продолжают), время — только с соседней сценой, где
    тот же день назван явно.
    """
    out: list[dict] = []
    last: dict | None = None       # последняя сцена с явным днём или датой
    prev: dict | None = None       # предыдущая сцена со временем

    def warn(s: dict, msg: str) -> None:
        out.append({"scene_id": s.get("id"), "title": s.get("title") or "без названия", "message": msg})

    for s in scenes:
        cur = parse(s.get("time_of_day", ""))
        if cur["flashback"]:
            continue
        cur["title"] = s.get("title") or "без названия"
        cur["text"] = s.get("time_of_day", "")
        explicit = cur["weekday"] is not None or cur["date"] is not None
        if last is not None and explicit:
            pw, cw, pd, cd = last["weekday"], cur["weekday"], last["date"], cur["date"]
            ref = f"«{last['title']}»"
            adjacent = prev is last
            if pd and cd and _day_of_year(cd) < _day_of_year(pd):
                warn(s, f"дата {_ddmm(cd)} раньше, чем в сцене {ref} ({_ddmm(pd)})")
            elif pd and cd and pw is not None and cw is not None \
                    and (_day_of_year(cd) - _day_of_year(pd) - (cw - pw)) % 7:
                warn(s, f"{_ddmm(cd)} — {_WD_NAMES[cw]}, а {_ddmm(pd)} в {ref} — {_WD_NAMES[pw]}: "
                        f"даты и дни недели не сходятся")
            elif cur["next_day"] and adjacent and pw is not None and cw is not None \
                    and cw != (pw + 1) % 7:
                warn(s, f"«на следующий день» после {ref} ({_WD_NAMES[pw]}), а здесь {_WD_NAMES[cw]}")
            elif pw is not None and cw is not None and cw != pw and not cur["gap"] \
                    and not (pd and cd) and (cw - pw) % 7 >= 4:
                warn(s, f"{_WD_NAMES[cw]} после сцены {ref} ({_WD_NAMES[pw]}) — прошло "
                        f"{(cw - pw) % 7} дн.? Если нет, день недели перепутан")
            same_day = adjacent and not cur["next_day"] and not cur["gap"] and (
                (cd is not None and cd == pd) or (cd is None and pd is None and cw is not None and cw == pw))
            if same_day and last["minutes"] is not None and cur["minutes"] is not None \
                    and cur["minutes"] < last["minutes"]:
                warn(s, f"тот же день, что в {ref}, но время раньше: «{cur['text']}» после «{last['text']}»")
        if cur["weekday"] is None and cur["next_day"] and prev is not None and prev is last \
                and last["weekday"] is not None:
            cur["weekday"] = (last["weekday"] + 1) % 7      # «на следующий день» после явного дня
            explicit = True
        if cur["weekday"] is not None or cur["date"] is not None or cur["minutes"] is not None:
            prev = cur
        if explicit:
            last = cur
    return out