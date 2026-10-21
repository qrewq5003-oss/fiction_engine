"""
run_ahead.py — сторож забеганий: глава раскрыла то, что по плану позже.

Книга «Фон» (24 главы, 19.10) писалась с внешним сторожем: после каждой главы
модель другого семейства, чем писатель, сверяла главу с планами СЛЕДУЮЩИХ
глав. Он поймал четыре настоящих раскрытия (гл.4, 7, 9, 11): совпадение
брелока и татуировки на две главы раньше, признание Гоши на восемь глав
раньше. Приложение их не видело: у «Мастерской» есть только план своей главы,
а в его «пока не раскрывать» из четырёх раскрытий попадало одно.

Планы вперёд присылает планировщик вместе с планом главы (сцены доски после
неё). Они хранятся отдельно и идут только сторожу — писателю никогда: план
вперёд в задаче и есть забегание. Что уже известно читателю — карточки
персонажей, мир и прошлые главы (L3, иначе их планы): без прошлых глав сторож
на гл.13 принял за забегание признание из гл.10. «Сюжет и арки» в известное
не входит — из него писатель «Фона» раскрыл гл.2 в гл.1. «Заметки автора»
не уходят никуда.

Находка без дословной цитаты из главы отбрасывается: сторож мог её выдумать.
"""

from __future__ import annotations

import re
from typing import Callable

from .db_core import get_conn

FUTURE_MAX = 12000           # символов плана вперёд в запросе
PAST_MAX = 15000             # символов прошлых глав: при 6000 ранние главы выпадали (разбор 21.10)
QUOTE_MIN_WORDS = 4
KINDS = ("раскрытие", "деталь")


def _ensure() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chapter_future_plans (
                project_id  INTEGER NOT NULL REFERENCES projects(id),
                chapter_num INTEGER NOT NULL,
                text        TEXT NOT NULL,
                saved_at    TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (project_id, chapter_num)
            )""")


def save_future(project_id: int, chapter_num: int, text: str) -> None:
    """План вперёд на момент плана главы chapter_num. Пусто — запись убирается."""
    _ensure()
    with get_conn() as conn:
        if (text or "").strip():
            conn.execute("INSERT INTO chapter_future_plans (project_id, chapter_num, text) VALUES (?,?,?) "
                         "ON CONFLICT(project_id, chapter_num) DO UPDATE SET text=excluded.text, "
                         "saved_at=datetime('now')", (project_id, chapter_num, text.strip()))
        else:
            conn.execute("DELETE FROM chapter_future_plans WHERE project_id=? AND chapter_num=?",
                         (project_id, chapter_num))


def get_future(project_id: int, chapter_num: int) -> str:
    """
    План вперёд для главы chapter_num: снимок доски на момент её плана, но
    главы, чей план с тех пор пришёл в FE, — их нынешним планом. Снимок
    устаревал: план всей книги отправлен заранее, позже главу 15 перепланировали,
    а сторож гл.12 сверялся со старой гл.15 (разбор планировщика 21.10).
    """
    _ensure()
    with get_conn() as conn:
        row = conn.execute("SELECT text FROM chapter_future_plans WHERE project_id=? AND chapter_num=?",
                           (project_id, chapter_num)).fetchone()
        later = conn.execute(
            "SELECT after_chapter + 1, note FROM director_notes WHERE project_id=? AND after_chapter >= ? "
            "AND note LIKE 'ПЛАН ГЛАВЫ%' ORDER BY after_chapter", (project_id, chapter_num)).fetchall()
    stored = row[0] if row else ""
    if not stored:
        return ""
    fresh = {int(n): note for n, note in later if int(n) > chapter_num}
    from .db_narrative import without_continuation
    keep = [ln for ln in stored.splitlines()
            if not ((m := _CH_LINE.match(ln)) and int(m.group(1)) in fresh)]
    blocks = [f"- гл.{n} (план из FE): " + " ".join(without_continuation(note).split())[:1500]
              for n, note in sorted(fresh.items())]
    return "\n".join(keep + blocks).strip()


_CH_LINE = re.compile(r"^- гл\.(\d+)\b")


_PROMPT = """Ниже глава {num} книги, её план и планы СЛЕДУЮЩИХ глав. Найди, где
глава {num} ЗАБЕГАЕТ ВПЕРЁД — делает то, что по планам будет позже:
- уже произошло событие из плана следующих глав (найдена улика, признание,
  задержание, открыт груз, найден человек);
- раскрыто или названо то, что её план оставляет неизвестным, а планы
  следующих глав раскрывают позже: кто это был, чья вещь, кто виновен
  (например, план говорит «видел женщину», а в главе свидетель прямо называет
  её по имени);
- нарушено «пока не раскрывать» из плана этой главы.
НЕ забегание: догадки и подозрения героя; намёки и улики, которые лишь
указывают в сторону будущего, ничего не раскрывая, — честной истории такие
улики и нужны; то, что уже известно (персонажи, мир, прошлые главы).
Забегание — только когда читатель уже ЗНАЕТ то, что по плану узнаёт позже.

=== ПЛАН ЭТОЙ ГЛАВЫ ===
{own}

=== ИЗВЕСТНО С ПЕРВОЙ ГЛАВЫ (персонажи и мир — не забегание) ===
{known}
{past}
=== ПЛАНЫ СЛЕДУЮЩИХ ГЛАВ ===
{future}

=== ГЛАВА {num} ===
{text}

Каждой находке дай kind: «раскрытие» — читатель узнал то, что по плану узнаёт
позже (кто это был, кто виновен, признание, найдена ключевая улика, случилось
событие будущей главы); «деталь» — подробность из будущего плана появилась
раньше, но ничего не раскрыла. quote — точная цитата из главы, 8–20 слов подряд.
Нет забеганий — пустой список.

Ответь JSON без пояснений: {{"happened": [{{"plan": "гл.9 «…»", "kind": "раскрытие", "quote": "…", "why": "…"}}]}}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower().replace("ё", "е"))).strip()


def find_run_ahead(chapter_num: int, text: str, own_plan: str, future: str, known: str,
                   past: str, api_call_fn: Callable[[str], str]) -> list[dict]:
    """→ [{plan, kind, quote, why}] — только находки с цитатой, которая есть в главе."""
    if not (future or "").strip() or not (text or "").strip():
        return []
    from .pipeline_config import CRITIC_TEXT_LIMIT
    from .pipeline_llm import parse_json
    raw = api_call_fn(_PROMPT.format(
        num=chapter_num, own=(own_plan or "—").strip(), known=(known or "—").strip(),
        past=f"\n=== УЖЕ ПРОИЗОШЛО В ПРОШЛЫХ ГЛАВАХ (не забегание) ===\n{past.strip()}\n" if past.strip() else "",
        future=future.strip()[:FUTURE_MAX], text=text[:CRITIC_TEXT_LIMIT]))
    data = parse_json(raw)
    got = data.get("happened") if isinstance(data, dict) else data if isinstance(data, list) else None
    if not isinstance(got, list):
        raise ValueError("сторож забеганий: ответ модели не разобран")
    t = _norm(text)
    out = []
    for x in got:
        if not isinstance(x, dict):
            continue
        q = _norm(str(x.get("quote") or ""))
        if len(q.split()) < QUOTE_MIN_WORDS or q not in t:
            continue
        kind = str(x.get("kind") or "").strip().lower()
        out.append({"plan": str(x.get("plan") or "").strip(),
                    "kind": "раскрытие" if "раскр" in kind else "деталь",
                    "quote": str(x.get("quote") or "").strip(), "why": str(x.get("why") or "").strip()})
    return out


def _known(project_id: int) -> str:
    """Персонажи и мир из подготовки — без «Сюжета» и без «Заметок автора»."""
    from .db_settings import PREP_DEFAULTS, get_prep
    prep = get_prep(project_id)
    parts = [prep.get(s, "").strip() for s in ("characters", "world")]
    return "\n\n".join(p for p, s in zip(parts, ("characters", "world")) if p and p != PREP_DEFAULTS[s].strip())


def _past(project_id: int, chapter_num: int) -> str:
    """Что уже было: события L3 прошлых глав, иначе их план."""
    from .db_narrative import get_director_note, get_l3_summaries
    l3 = {s["chapter_num"]: (s.get("events") or "").strip()
          for s in get_l3_summaries(project_id, chapter_num, n=10_000)}
    lines = []
    for k in range(1, chapter_num):
        what = l3.get(k) or re.sub(r"\s+", " ", (get_director_note(project_id, k) or "").split("ПОКА НЕ РАСКРЫВАТЬ")[0]).strip()
        if what:
            lines.append(f"гл.{k}: {what}")
    return "\n".join(lines)[-PAST_MAX:]


def run_ahead_for(project_id: int, chapter_num: int, text: str,
                  api_call_fn: Callable[[str], str]) -> list[dict] | None:
    """Сторож для главы проекта. None — плана вперёд нет, проверять не с чем."""
    future = get_future(project_id, chapter_num)
    if not future:
        return None
    from .db_narrative import get_director_note
    return find_run_ahead(chapter_num, text, get_director_note(project_id, chapter_num) or "", future,
                          _known(project_id), _past(project_id, chapter_num), api_call_fn)
