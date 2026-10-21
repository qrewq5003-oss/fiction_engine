"""
db_state.py — State Engine: хранение и разбор.

Ответственность:
  - get/update/snapshot/restore state
  - parse_structured_state — структурированный разбор текста state
  - extract_freeform_with_llm — разбор свободного текста моделью

Слияние анализа главы в State — engine/state_merge.py; его публичные функции
доступны и отсюда, как раньше.
"""

import re
from collections import Counter
from typing import Callable
from .db_core import get_conn, _default_global, _default_plot, _default_memory
from .error_policy import handle_error, ErrorLevel
from .state_merge import (  # noqa: F401 — прежние точки входа
    SERIES_DETAILS_HEADER, SERIES_DETAILS_MAX, merge_analysis_into_state,
    merge_series_details, series_details, drop_series_details, detail_chapters,
)


# ─── CRUD ────────────────────────────────────────────────────────────────────

# created_at имеет секундную точность: две записи, сделанные подряд,
# получают одинаковую метку, и порядок между ними становится
# произвольным. id (AUTOINCREMENT) даёт устойчивый вторичный ключ —
# без него «последнее обновление» и «свежие правки» врали при любой
# паре записей внутри одной секунды.
STATE_FIELDS = ("global_state", "plot_matrix", "memory_graph")


def _lf(text: str | None) -> str | None:
    """
    Переводы строк Windows → \\n. State, поправленный в окне браузера,
    приходит с \\r\\n, и поиск заголовков в слиянии (`^### Имя$`) на таком
    тексте не срабатывал: каждый персонаж считался новым и дописывался
    дублем, разделы повторялись (у автора 17.10 — четыре персонажа дважды
    и по два «ОТКРЫТЫХ ВОПРОСА» и «ДЕТАЛИ СЕРИИ» после глав 2 и 3).
    """
    return text.replace("\r\n", "\n").replace("\r", "\n") if isinstance(text, str) else text


def get_state(project_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM state_engine WHERE project_id=?", (project_id,)
        ).fetchone()
        if not row:
            return {"global_state": _default_global(),
                    "plot_matrix":  _default_plot(),
                    "memory_graph": _default_memory()}
        d = dict(row)
        # Уже сохранённый с \r\n State читается нормальным — без миграции
        for k in STATE_FIELDS:
            d[k] = _lf(d.get(k))
        return d


def update_state(project_id: int, global_state: str | None = None,
                 plot_matrix: str | None = None, memory_graph: str | None = None,
                 _snapshot_reason: str = "") -> None:
    try:
        existing = get_state(project_id)
        if existing.get("global_state") or existing.get("plot_matrix"):
            snapshot_state(project_id, reason=_snapshot_reason or "авто")
    except Exception as e:
        handle_error(f"update_state({project_id}) snapshot", e, level=ErrorLevel.RECOVERABLE)

    state = get_state(project_id)
    new_global = _lf(global_state if global_state is not None else state["global_state"])
    new_plot   = _lf(plot_matrix  if plot_matrix  is not None else state["plot_matrix"])
    new_memory = _lf(memory_graph if memory_graph is not None else state["memory_graph"])
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO state_engine (project_id, global_state, plot_matrix, memory_graph, updated_at)
               VALUES (?,?,?,?,datetime('now'))
               ON CONFLICT(project_id) DO UPDATE SET
                 global_state=excluded.global_state,
                 plot_matrix=excluded.plot_matrix,
                 memory_graph=excluded.memory_graph,
                 updated_at=excluded.updated_at""",
            (project_id, new_global, new_plot, new_memory)
        )


def save_state_update(project_id: int, chapter_num: int, raw_analysis: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO state_updates (project_id, chapter_num, raw_analysis) VALUES (?,?,?)",
            (project_id, chapter_num, raw_analysis)
        )
        return cur.lastrowid


def mark_update_applied(project_id: int, update_id: int) -> bool:
    """Пометить обновление применённым. False — обновление чужого проекта.

    Раньше брала один update_id, и /state/apply, /state/discard гасили
    чужие ожидающие обновления: анализ соседнего проекта исчезал из
    очереди, не будучи применённым ни к одному состоянию.
    """
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE state_updates SET applied=1 WHERE id=? AND project_id=?",
            (update_id, project_id)
        )
        return cur.rowcount > 0


def get_pending_updates(project_id: int) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM state_updates WHERE project_id=? AND applied=0 "
            "ORDER BY created_at, id",
            (project_id,)
        ).fetchall()]


def get_last_update(project_id: int, before_chapter: int | None = None) -> dict | None:
    """Последний анализ главы; before_chapter — последний ПРИМЕНЁННЫЙ анализ глав до этой
    (раньше — последний любой: чужой главы, черновой, неприменённый)."""
    with get_conn() as conn:
        if before_chapter is None:
            row = conn.execute(
                "SELECT * FROM state_updates WHERE project_id=? "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (project_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM state_updates WHERE project_id=? AND applied=1 AND chapter_num < ? "
                "ORDER BY chapter_num DESC, id DESC LIMIT 1",
                (project_id, before_chapter)
            ).fetchone()
        return dict(row) if row else None


# ─── Снапшоты ─────────────────────────────────────────────────────────────────

SNAPSHOT_BEFORE = "перед анализом гл."     # + номер: State до анализа этой главы

def snapshot_state(project_id: int, reason: str = "") -> None:
    state = get_state(project_id)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO state_history
               (project_id, global_state, plot_matrix, memory_graph, reason, saved_at)
               VALUES (?,?,?,?,?,datetime('now'))""",
            (project_id,
             state.get("global_state", ""),
             state.get("plot_matrix", ""),
             state.get("memory_graph", ""),
             reason)
        )
        # Хранится 20 последних снимков, кроме «перед анализом гл.N»: по ним
        # «Откатить главу» и State на момент главы (state_for_chapter). Они
        # вытеснялись — в 24 главах «Фона» снимка до ранних глав уже не было
        conn.execute("""
            DELETE FROM state_history WHERE project_id=? AND reason NOT LIKE ? AND id NOT IN (
                SELECT id FROM state_history WHERE project_id=? AND reason NOT LIKE ?
                ORDER BY id DESC LIMIT 20
            )""", (project_id, SNAPSHOT_BEFORE + "%", project_id, SNAPSHOT_BEFORE + "%"))


def get_state_history(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, reason, saved_at FROM state_history WHERE project_id=? ORDER BY id DESC",
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def snapshot_before_chapter(project_id: int, chapter_num: int) -> dict | None:
    """
    Снимок State до анализа главы: первый «перед анализом гл.N» после
    анализа последней из прежних глав. Глава принималась дважды — первый,
    иначе в State остался бы её прежний вариант. None — снимка нет (глава
    принята до этих пометок или снимок вытеснен: их хранится 20).
    """
    import re
    with get_conn() as conn:
        rows = conn.execute("SELECT id, reason, saved_at FROM state_history WHERE project_id=? "
                            "AND reason LIKE ? ORDER BY id", (project_id, SNAPSHOT_BEFORE + "%")).fetchall()
    marked = [(dict(r), int(m.group(1))) for r in rows
              if (m := re.fullmatch(re.escape(SNAPSHOT_BEFORE) + r"(\d+)", r["reason"] or ""))]
    after = max((r["id"] for r, n in marked if n < chapter_num), default=0)
    return next((r for r, n in marked if n == chapter_num and r["id"] > after), None)


# Снимок при анализе главы, после которой уже есть принятые (переписывание
# главы из середины книги): «Откатить главу» и state_for_chapter его не берут
SNAPSHOT_RECOMPUTE = "перед пересчётом гл."


def state_for_chapter(project_id: int, chapter_num: int) -> dict:
    """
    State, который видит работа над главой N: для новой главы — нынешний, для
    уже принятой (её переписывают) — снимок до её анализа, то есть State после
    глав до неё. Раньше всегда нынешний: писатель переписываемой гл.12 «Фона»
    получил бы «Марат обвинён», «МОМЕНТ 6.12» и всю разгадку в «ЗНАЕТ» героини
    (разбор 21.10). Снимка нет (старая книга: снимки вытеснялись) — нынешний.
    """
    if chapter_num:
        from .db_chapters import last_chapter_number
        last = last_chapter_number(project_id)
        if last and chapter_num <= last:
            snap = snapshot_before_chapter(project_id, chapter_num)
            if snap:
                with get_conn() as conn:
                    row = conn.execute("SELECT * FROM state_history WHERE id=?", (snap["id"],)).fetchone()
                return {k: _lf(row[k]) for k in STATE_FIELDS}
            # Старая книга: снимков до глав нет (вытеснялись). State — конец
            # книги; его «сейчас» (где, что дальше, что знают герои) — будущее
            # для этой главы: не отдаём, автору — предупреждение (разбор 21.10)
            from .engine_issues import note_engine_issue
            note_engine_issue(f"нет снимка State до гл.{chapter_num} — работе над ней не даны поля «сейчас» "
                              "(где герои, что знают, что дальше): они с конца книги")
            st = without_now_fields(get_state(project_id))
            # И детали серии этой главы и поздних
            from .state_merge import drop_series_details
            return {**st, "plot_matrix": drop_series_details(st["plot_matrix"], set(range(chapter_num, last + 1)))}
    return get_state(project_id)


# Поля «сейчас» State: на конец книги они — будущее для главы из середины
_NOW_KEYS = ("СОСТОЯНИЕ", "Состояние", "Статус", "ЛОКАЦИЯ", "Локация", "Место", "ЦЕЛЬ_СЕЙЧАС", "Цель текущая",
             "Цель сейчас", "ЗНАЕТ", "Знает", "НЕ_ЗНАЕТ", "Не знает", "ДУМАЕТ_ЧТО_ЗНАЕТ", "МОМЕНТ", "Момент",
             "Текущий момент", "УГРОЗА", "НЕ_ДОЛЖНО_СЛУЧИТЬСЯ", "ГДЕ_СЕЙЧАС", "Где сейчас", "СЛЕДУЮЩИЙ_ШАГ",
             "Следующий шаг", "СТАТУС", "ИЗМЕНЕНИЕ")
_NOW_LINE = re.compile(r"^\s*(?:" + "|".join(map(re.escape, _NOW_KEYS)) + r")\s*[:\-][^\n]*\n?", re.M)


def without_now_fields(state: dict) -> dict:
    """State без полей «сейчас» и без «кто что знает»: карточки, линии, детали — остаются."""
    return {**state, "global_state": _NOW_LINE.sub("", state.get("global_state") or ""),
            "plot_matrix": _NOW_LINE.sub("", state.get("plot_matrix") or ""), "memory_graph": ""}


def restore_state_snapshot(project_id: int, snapshot_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM state_history WHERE id=? AND project_id=?",
            (snapshot_id, project_id)
        ).fetchone()
    if not row:
        return False
    snapshot_state(project_id, reason="авто-снапшот перед откатом")
    update_state(project_id, row["global_state"], row["plot_matrix"], row["memory_graph"])
    return True


# ─── Парсинг State ────────────────────────────────────────────────────────────

_EXCLUDE_WORDS = {
    "Его", "Её", "Они", "Она", "Оно", "Это", "Так", "Вот", "Там", "Тут",
    "Всё", "Уже", "Ещё", "Нет", "Да", "Но", "Как", "Что", "Где", "Когда",
    "Если", "Потому", "Также", "При", "Главный", "Главная", "Первый",
    "Первая", "Новый", "Новая", "Старый", "Старая", "Большой", "Другой",
    "Другая", "Такой", "Такая", "Сам", "Сама", "Один", "Одна", "Весь", "Вся",
    "Мир", "Мире", "Время", "Место", "Линия", "Цель", "Угроза",
}


# Незаполненное поле шаблона State: «[]», «[что нельзя допустить в следующей
# главе]». Писатель «Фона» получал его как «⚠ НЕЛЬЗЯ: [что нельзя допустить…]»
# (разбор 21.10)
_TEMPLATE_VALUE = re.compile(r"\[[^\]]*\]")


def _extract_field(text: str, *keys: str) -> str:
    for key in keys:
        m = re.search(rf"(?:{re.escape(key)})\s*[:\-]\s*([^\n]+)", text, re.IGNORECASE)
        v = m.group(1).strip() if m else ""
        if v not in ("", "-") and not _TEMPLATE_VALUE.fullmatch(v):
            return v
    return ""


def _extract_block(text: str, header: str) -> str:
    m = re.search(rf"###\s*{re.escape(header)}" + r"(.*?)(?=###|---|\Z)", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _detect_char_names_freeform(global_text: str) -> list[str]:
    """Извлечь имена персонажей из свободного текста по частотности."""
    candidates = re.findall(r"\b([А-ЯЁ][а-яё]{2,12})\b", global_text)
    counts = Counter(candidates)
    names = []
    for w, c in counts.items():
        if w in _EXCLUDE_WORDS or len(w) < 3:
            continue
        if c >= 2 or re.search(rf"\b{w}\s+[а-яё]", global_text):
            names.append(w)
    return names[:4]


def _empty_structured_state(state: dict) -> dict:
    return {"characters": {}, "char_names": [], "world": {}, "plot": {}, "raw": state}


def parse_structured_state(state: dict) -> dict:
    """
    Парсит State Engine в структурированный словарь.
    При ошибке возвращает пустую структуру — вызывающий код продолжит работу.
    """
    try:
        return _parse_structured_state_impl(state)
    except Exception as e:
        handle_error("parse_structured_state", e, level=ErrorLevel.RECOVERABLE)
        return _empty_structured_state(state)


def _parse_structured_state_impl(state: dict) -> dict:
    global_text = state.get("global_state", "")
    plot_text   = state.get("plot_matrix", "")

    char_names = re.findall(r"###\s+([^\n\[]+)", global_text)
    char_names = [n.strip() for n in char_names if "[" not in n]

    if not char_names and global_text.strip():
        char_names = _detect_char_names_freeform(global_text)

    characters = {}
    for name in char_names:
        block = _extract_block(global_text, name)
        characters[name] = {
            "state":     _extract_field(block, "СОСТОЯНИЕ", "Состояние", "STATE"),
            "location":  _extract_field(block, "ЛОКАЦИЯ", "Локация", "LOCATION"),
            "goal":      _extract_field(block, "ЦЕЛЬ_СЕЙЧАС", "Цель текущая", "GOAL"),
            "deep_goal": _extract_field(block, "ЦЕЛЬ_ГЛУБИННАЯ", "Цель глубинная"),
            "knows":     _extract_field(block, "ЗНАЕТ", "Знает", "KNOWS"),
            "ignores":   _extract_field(block, "НЕ_ЗНАЕТ", "Не знает"),
        }

    world = {
        "moment":    _extract_field(global_text, "МОМЕНТ", "Текущий момент"),
        "threat":    _extract_field(global_text, "УГРОЗА", "Основная угроза"),
        "forbidden": _extract_field(global_text, "НЕ_ДОЛЖНО_СЛУЧИТЬСЯ", "Нельзя допустить"),
    }

    plot = {
        "status":   _extract_field(plot_text, "СТАТУС", "Статус"),
        "where":    _extract_field(plot_text, "ГДЕ_СЕЙЧАС", "Где сейчас"),
        "next":     _extract_field(plot_text, "СЛЕДУЮЩИЙ_ШАГ", "Следующий шаг"),
        "must_not": _extract_field(plot_text, "ЧТО НЕЛЬЗЯ ЗАБЫТЬ"),
    }

    return {
        "characters": characters,
        "char_names": char_names,
        "world":      world,
        "plot":       plot,
        "raw":        state,
    }


def get_structured_state(project_id: int) -> dict:
    return parse_structured_state(get_state(project_id))


# ─── LLM-экстракция freeform state ───────────────────────────────────────────

_SYS_FREEFORM_EXTRACT = """Ты — ассистент структурирования данных.
Тебе дан свободный текст о персонажах и состоянии истории.
Извлеки структурированные данные в JSON. Отвечай ТОЛЬКО валидным JSON, без текста до и после."""

_PROMPT_FREEFORM_EXTRACT = """Из этого текста извлеки данные о персонажах и мире истории:

{text}

Верни JSON в формате:
{{
  "characters": [
    {{
      "name": "Имя",
      "state": "эмоциональное/физическое состояние",
      "location": "где находится",
      "goal": "текущая цель",
      "knows": "ключевое знание",
      "ignores": "чего не знает"
    }}
  ],
  "world": {{
    "moment": "текущий момент истории (1 предложение)",
    "threat": "главная угроза или напряжение",
    "forbidden": "что нельзя допустить"
  }},
  "plot": {{
    "next": "следующий сюжетный шаг",
    "must_not": "что нельзя забыть"
  }}
}}

Если информации нет — пустая строка в поле.
Только персонажи которые явно упомянуты. Не придумывай."""


def extract_freeform_with_llm(freeform_text: str,
                              api_call_fn: Callable[[str], str] | None) -> dict | None:
    """
    Извлечь структурированные данные из свободного текста через LLM.

    Возвращает dict совместимый с parse_structured_state или None при ошибке.
    Вызывать только когда structured parsing вернул пустой результат.

    api_call_fn: callable(prompt: str) -> str  — лёгкая модель (haiku/flash).
    """
    if not freeform_text or not freeform_text.strip():
        return None
    if not api_call_fn:
        return None

    try:
        import json
        prompt = _PROMPT_FREEFORM_EXTRACT.format(text=freeform_text[:2000])
        raw = api_call_fn(prompt)

        from .pipeline_llm import parse_json
        data = parse_json(raw)
        if not isinstance(data, dict):
            raise ValueError("модель не вернула объект")

        # Конвертируем в формат parse_structured_state
        characters = {}
        char_names = []
        for ch in data.get("characters", []):
            name = ch.get("name", "").strip()
            if not name:
                continue
            char_names.append(name)
            characters[name] = {
                "state":    ch.get("state", ""),
                "location": ch.get("location", ""),
                "goal":     ch.get("goal", ""),
                "knows":    ch.get("knows", ""),
                "ignores":  ch.get("ignores", ""),
            }

        world_raw = data.get("world", {})
        plot_raw  = data.get("plot", {})

        return {
            "characters": characters,
            "char_names": char_names,
            "world": {
                "moment":    world_raw.get("moment", ""),
                "threat":    world_raw.get("threat", ""),
                "forbidden": world_raw.get("forbidden", ""),
            },
            "plot": {
                "next":     plot_raw.get("next", ""),
                "must_not": plot_raw.get("must_not", ""),
            },
            "raw": {},
            "_source": "llm_freeform",
        }
    except Exception as e:
        handle_error("extract_freeform_with_llm", e, level=ErrorLevel.RECOVERABLE)
        return None


def parse_structured_state_smart(state: dict,
                                 api_call_fn: Callable[[str], str] | None = None) -> dict:
    """
    Улучшенный парсер: сначала structured parsing, при пустом результате — LLM.

    Используй вместо parse_structured_state() когда доступен api_call_fn.
    Совместим по формату возврата.
    """
    result = parse_structured_state(state)

    # Если structured parsing вернул данные — готово
    if result["char_names"]:
        return result

    # Пробуем LLM если есть freeform текст и caller
    global_text = state.get("global_state", "")
    if global_text.strip() and api_call_fn:
        llm_result = extract_freeform_with_llm(global_text, api_call_fn)
        if llm_result and llm_result["char_names"]:
            return llm_result

    return result
