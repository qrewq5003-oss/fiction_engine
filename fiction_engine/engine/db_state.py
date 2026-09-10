"""
db_state.py — State Engine: хранение, парсинг, слияние анализа.

Ответственность:
  - get/update/snapshot/restore state
  - parse_structured_state — структурированный разбор текста state
  - merge_analysis_into_state — применение анализа главы к state
"""

import re
from collections import Counter
from .db_core import get_conn, _default_global, _default_plot, _default_memory
from .error_policy import handle_error, ErrorLevel


# ─── CRUD ────────────────────────────────────────────────────────────────────

# created_at имеет секундную точность: две записи, сделанные подряд,
# получают одинаковую метку, и порядок между ними становится
# произвольным. id (AUTOINCREMENT) даёт устойчивый вторичный ключ —
# без него «последнее обновление» и «свежие правки» врали при любой
# паре записей внутри одной секунды.
def get_state(project_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM state_engine WHERE project_id=?", (project_id,)
        ).fetchone()
        if not row:
            return {"global_state": _default_global(),
                    "plot_matrix":  _default_plot(),
                    "memory_graph": _default_memory()}
        return dict(row)


def update_state(project_id: int, global_state: str = None,
                 plot_matrix: str = None, memory_graph: str = None,
                 _snapshot_reason: str = ""):
    try:
        existing = get_state(project_id)
        if existing.get("global_state") or existing.get("plot_matrix"):
            snapshot_state(project_id, reason=_snapshot_reason or "авто")
    except Exception as e:
        handle_error(f"update_state({project_id}) snapshot", e, level=ErrorLevel.RECOVERABLE)

    state = get_state(project_id)
    new_global = global_state if global_state is not None else state["global_state"]
    new_plot   = plot_matrix  if plot_matrix  is not None else state["plot_matrix"]
    new_memory = memory_graph if memory_graph is not None else state["memory_graph"]
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


def mark_update_applied(update_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE state_updates SET applied=1 WHERE id=?", (update_id,))


def get_pending_updates(project_id: int) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM state_updates WHERE project_id=? AND applied=0 "
            "ORDER BY created_at, id",
            (project_id,)
        ).fetchall()]


def get_last_update(project_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM state_updates WHERE project_id=? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (project_id,)
        ).fetchone()
        return dict(row) if row else None


# ─── Снапшоты ─────────────────────────────────────────────────────────────────

def snapshot_state(project_id: int, reason: str = ""):
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
        conn.execute("""
            DELETE FROM state_history WHERE project_id=? AND id NOT IN (
                SELECT id FROM state_history WHERE project_id=?
                ORDER BY id DESC LIMIT 20
            )""", (project_id, project_id))


def get_state_history(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, reason, saved_at FROM state_history WHERE project_id=? ORDER BY id DESC",
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


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


def _extract_field(text: str, *keys) -> str:
    for key in keys:
        m = re.search(rf"(?:{re.escape(key)})\s*[:\-]\s*([^\n]+)", text, re.IGNORECASE)
        if m and m.group(1).strip() not in ("[]", "", "-"):
            return m.group(1).strip()
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


# ─── Слияние анализа в State ──────────────────────────────────────────────────

def _is_real_value(val: str) -> bool:
    """Значение не пустое, не плейсхолдер и не 'без изменений'."""
    return bool(val) and not val.startswith("[") and "без изменений" not in val.lower()


# ─── Терпимый разбор полей State Engine ───────────────────────────────────────
#
# В проекте исторически сосуществуют три написания одних и тех же полей:
#   • db_core._default_global()            → СОСТОЯНИЕ: ЛОКАЦИЯ: ЦЕЛЬ_СЕЙЧАС: ЗНАЕТ:
#   • 08_STATE_ENGINE/global_state_template.md → Состояние: Локация: Цель текущая: Знает:
#   • реальные проекты авторов             → Статус: Место: Цель: и другие вариации
#
# Раньше парсер искал только ВЕРХНИЙ регистр и регистрозависимо, поэтому на
# двух форматах из трёх не находил ничего, ничего не менял — но всё равно
# сообщал об изменении. Ниже — терпимое сопоставление по синонимам.

FIELD_ALIASES: dict[str, list[str]] = {
    "состояние": ["СОСТОЯНИЕ", "Состояние", "Статус", "СТАТУС"],
    "локация":   ["ЛОКАЦИЯ", "Локация", "Место", "МЕСТО"],
    "цель":      ["ЦЕЛЬ_СЕЙЧАС", "Цель текущая", "Цель сейчас", "ЦЕЛЬ", "Цель"],
    "знает":     ["ЗНАЕТ", "Знает"],
    "не_знает":  ["НЕ_ЗНАЕТ", "Не знает"],
    "момент":    ["МОМЕНТ", "Момент", "Текущий момент"],
    "статус":    ["СТАТУС", "Статус"],
    "след_шаг":  ["СЛЕДУЮЩИЙ_ШАГ", "Следующий шаг", "СЛЕДУЮЩИЙ ШАГ"],
}


def _field_pattern(alias: str) -> str:
    """
    Регексп строки поля: отступ, написание ключа, значение, хвостовой CR.

    Группа 4 (\r) отделена специально: файлы State, пришедшие из Windows,
    хранятся в CRLF, и без этого значение поля забирало бы \r внутрь,
    а перезапись строки ломала бы единообразие переводов строк.
    """
    return rf"^([ \t]*)({re.escape(alias)})[ \t]*:[ \t]*([^\r\n]*)(\r?)$"


def _find_field(text: str, field_key: str, fallback_key: str = ""):
    """
    Найти строку поля по любому из известных написаний, регистронезависимо.
    Возвращает re.Match с группами (отступ, ключ-как-в-тексте, значение) или None.
    """
    aliases = list(FIELD_ALIASES.get(field_key, []))
    if fallback_key and fallback_key not in aliases:
        aliases.append(fallback_key)
    # Синонимы перебираются по порядку списка, а не одной альтернативой:
    # так каноничное написание побеждает приблизительное, если в блоке
    # присутствуют оба (например "Состояние" рядом со "Статус").
    for alias in aliases:
        m = re.search(_field_pattern(alias), text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m
    return None


def _key_style(block: str, aliases: list[str]) -> str:
    """
    Выбрать написание ключа для нового поля так, чтобы оно совпало со стилем блока.
    Если в блоке ключи в ВЕРХНЕМ регистре — берём верхний вариант, иначе Title Case.
    """
    keys = re.findall(r"^[ \t]*([А-ЯЁA-Za-zа-яё_ ]+):", block, re.MULTILINE)
    upper = sum(1 for k in keys if k.strip() and k.strip() == k.strip().upper())
    if keys and upper * 2 >= len(keys):
        return next((a for a in aliases if a == a.upper()), aliases[0])
    return next((a for a in aliases if a != a.upper()), aliases[0])


def _append_field(block: str, key: str, value: str) -> str:
    """
    Дописать поле в конец блока, сохранив отступ и стиль переводов строк.
    В CRLF-документе новая строка тоже будет CRLF.
    """
    crlf = "\r\n" in block
    body = block.rstrip("\r\n")
    lines = body.split("\n")
    indent = ""
    for ln in reversed(lines):
        m = re.match(r"^([ \t]*)[^\s].*:", ln)
        if m:
            indent = m.group(1)
            break
    new_line = f"{indent}{key}: {value}" + ("\r" if crlf else "")
    tail = block[len(body):]
    return "\n".join(lines + [new_line]) + tail


def _apply_char_field(field_key: str, regex_key: str, new_val: str,
                      char_block: str, char_name: str,
                      record_fn) -> str:
    """
    Обновить одно поле персонажа в блоке. Возвращает обновлённый блок.

    Терпим к написанию ключа (см. FIELD_ALIASES). Если поля в блоке нет —
    дописывает его в стиле блока. record_fn вызывается ТОЛЬКО если текст
    действительно изменился: иначе интерфейс рапортовал бы о несделанных правках.
    """
    if not _is_real_value(new_val):
        return char_block
    if "→" in new_val:
        new_val = new_val.split("→", 1)[1].strip()

    m = _find_field(char_block, field_key, regex_key)
    if m:
        old_val = m.group(3).strip()
        updated = (char_block[:m.start()]
                   + f"{m.group(1)}{m.group(2)}: {new_val}{m.group(4)}"
                   + char_block[m.end():])
    else:
        old_val = ""
        aliases = list(FIELD_ALIASES.get(field_key, [])) or [regex_key]
        updated = _append_field(char_block, _key_style(char_block, aliases), new_val)

    if updated != char_block:
        record_fn(f"{char_name}.{field_key.lower()}", old_val, new_val)
    return updated


# ─── Терпимый поиск блока персонажа ──────────────────────────────────────────
#
# Заголовки персонажей в реальных проектах встречаются минимум в трёх видах:
#   ### Имя                       — шаблон движка
#   [ИМЯ ВАВРА — ГЛАВНЫЙ ГЕРОЙ]   — авторский формат
#   **Имя**                       — markdown-выделение
# Раньше искался только "### Имя", поэтому на остальных форматах персонаж
# считался несуществующим и дописывался заново — дублем в чужом стиле.

_HEADER_ANY = (r"(?:^#{2,4}[ \t]*\S"
               r"|^\[[^\]\r\n]+\][ \t\r]*$"
               r"|^\*\*[^*\r\n]+\*\*[ \t\r]*$)")


def _char_block_pattern(name: str) -> str:
    """Регексп: заголовок персонажа (любой стиль) + тело до следующего заголовка."""
    n = re.escape(name)
    header = (
        rf"(?:^#{{2,4}}[ \t]*{n}\b[^\r\n]*$"
        rf"|^\[[ \t]*{n}\b[^\]\r\n]*\][ \t\r]*$"
        rf"|^\*\*[ \t]*{n}\b[^*\r\n]*\*\*[ \t\r]*$)"
    )
    return rf"({header}\n)((?:(?!{_HEADER_ANY}).*\n?)*)"


def _find_char_block(global_text: str, name: str):
    """Найти блок персонажа по имени в любом из форматов заголовка."""
    if not name:
        return None
    return re.search(_char_block_pattern(name), global_text,
                     re.IGNORECASE | re.MULTILINE)


def _apply_doc_field(field_key: str, fallback_key: str, new_val: str,
                     text: str, record_name: str, record_fn) -> str:
    """
    Обновить поле уровня документа (Сюжет.СТАТУС, Мир.МОМЕНТ и т.п.).

    В отличие от полей персонажа, отсутствующее поле здесь НЕ дописывается:
    у документа нет однозначного места для вставки. Запись в отчёт — только
    при фактическом изменении текста.
    """
    m = _find_field(text, field_key, fallback_key)
    if not m:
        return text
    old_val = m.group(3).strip()
    updated = text[:m.start()] + f"{m.group(1)}{m.group(2)}: {new_val}{m.group(4)}" + text[m.end():]
    if updated != text:
        record_fn(record_name, old_val, new_val)
    return updated


def _apply_char_knows(knows_val: str, char_block: str, char_name: str, record_fn) -> str:
    """
    Дописать новое знание к полю ЗНАЕТ персонажа.

    Терпим к написанию (ЗНАЕТ / Знает). Если поля нет — создаёт его.
    """
    if not _is_real_value(knows_val):
        return char_block

    knows_m = _find_field(char_block, "знает")
    if not knows_m:
        aliases = FIELD_ALIASES["знает"]
        updated = _append_field(char_block, _key_style(char_block, aliases), knows_val)
        if updated != char_block:
            record_fn(f"{char_name}.знает", "", knows_val)
        return updated

    existing = knows_m.group(3).strip().rstrip(",").rstrip(";").strip()
    new_knows = (existing + "; " + knows_val) if existing and existing != "[]" else knows_val
    updated = (char_block[:knows_m.start(3)] + new_knows + char_block[knows_m.end(3):])
    if updated != char_block:
        record_fn(f"{char_name}.знает", existing, new_knows)
    return updated


def _apply_existing_char(name: str, section: str, global_text: str, record_fn) -> str:
    """Применить обновления к существующему персонажу. Возвращает обновлённый global_text."""
    fields = {
        "состояние": re.search(r"состояние:\s*(.+?)(?:\n|$)", section),
        "локация":   re.search(r"локация:\s*(.+?)(?:\n|$)", section),
        "цель":      re.search(r"цель:\s*(.+?)(?:\n|$)", section),
        "узнал":     re.search(r"узнал:\s*(.+?)(?:\n|$)", section),
    }

    char_m = _find_char_block(global_text, name)
    if not char_m:
        return global_text

    block = char_m.group(2)

    if fields["состояние"]:
        block = _apply_char_field("состояние", "СОСТОЯНИЕ", fields["состояние"].group(1).strip(),
                                   block, name, record_fn)
    if fields["локация"]:
        block = _apply_char_field("локация", "ЛОКАЦИЯ", fields["локация"].group(1).strip(),
                                   block, name, record_fn)
    if fields["цель"]:
        block = _apply_char_field("цель", "ЦЕЛЬ_СЕЙЧАС", fields["цель"].group(1).strip(),
                                   block, name, record_fn)
    if fields["узнал"]:
        block = _apply_char_knows(fields["узнал"].group(1).strip(), block, name, record_fn)

    return global_text[:char_m.start(2)] + block + global_text[char_m.end(2):]


def _add_new_char(name: str, section: str, global_text: str, record_fn,
                  new_chars: list) -> str:
    """Добавить нового персонажа в global_text."""
    fields = {
        "состояние": re.search(r"состояние:\s*(.+?)(?:\n|$)", section),
        "локация":   re.search(r"локация:\s*(.+?)(?:\n|$)", section),
        "цель":      re.search(r"цель:\s*(.+?)(?:\n|$)", section),
    }

    def _val(key):
        m = fields.get(key)
        return m.group(1).strip() if m else ""

    state_val = _val("состояние")
    new_entry = _create_char_entry(name, state_val, _val("локация"), _val("цель"))

    if "## ПЕРСОНАЖИ" in global_text:
        global_text = global_text.replace("## ПЕРСОНАЖИ", "## ПЕРСОНАЖИ" + new_entry, 1)
    else:
        global_text += "\n" + new_entry

    new_chars.append(name)
    display_val = state_val if _is_real_value(state_val) else "добавлен"
    record_fn(f"{name} (новый персонаж)", "", display_val)
    return global_text


def _create_char_entry(name: str, state_val: str, loc_val: str, goal_val: str) -> str:
    """
    Единственный шаблон нового персонажа для global_state.

    Используется и в _add_new_char (legacy-путь) и в _merge_from_json.
    Любое добавление поля — только здесь.
    """
    def _clean(v: str) -> str:
        if not v or not _is_real_value(v):
            return "[]"
        if "→" in v:
            v = v.split("→", 1)[1].strip()
        return v

    return (
        f"\n### {name}\n"
        f"СОСТОЯНИЕ: {_clean(state_val)}\n"
        f"ЛОКАЦИЯ: {_clean(loc_val)}\n"
        f"ЦЕЛЬ_СЕЙЧАС: {_clean(goal_val)}\n"
        f"ЦЕЛЬ_ГЛУБИННАЯ: []\n"
        f"ЗНАЕТ: []\n"
        f"НЕ_ЗНАЕТ: []\n"
        f"ИЗМЕНЕНИЕ: [автодобавлен]\n"
    )


def _apply_global_block(gblock: str, global_text: str,
                        record_fn, new_chars: list) -> str:
    """Применить секцию GLOBAL_STATE к тексту состояния."""
    SKIP_NAMES = {"Мир", "МИР", "Новые линии", "Закрытые линии"}
    char_sections = re.split(r"\n(?=[А-ЯЁA-Z][^\n:]{1,40}:)", gblock)
    for section in char_sections:
        section = section.strip()
        if not section:
            continue
        name_m = re.match(r"^([А-ЯЁA-Z][^\n:]{1,40}):", section)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        if name in SKIP_NAMES:
            continue

        char_exists = re.search(
            rf"###\s*{re.escape(name)}\n", global_text, re.IGNORECASE
        )
        if char_exists:
            global_text = _apply_existing_char(name, section, global_text, record_fn)
        else:
            global_text = _add_new_char(name, section, global_text, record_fn, new_chars)

    return global_text


def _apply_plot_block(pblock: str, plot_text: str, record_fn) -> str:
    """Применить секцию PLOT_MATRIX к тексту сюжета."""
    next_step_m = re.search(r"следующий шаг:\s*(.+?)(?:\n|$)", pblock)
    if not next_step_m:
        return plot_text
    val = next_step_m.group(1).strip()
    if not _is_real_value(val):
        return plot_text
    old_m = re.search(r"СЛЕДУЮЩИЙ_ШАГ:\s*(.*)", plot_text)
    old_val = old_m.group(1).strip() if old_m else ""
    new_plot = re.sub(r"(СЛЕДУЮЩИЙ_ШАГ:\s*).*", f"СЛЕДУЮЩИЙ_ШАГ: {val}", plot_text)
    record_fn("Сюжет.следующий_шаг", old_val, val)
    return new_plot


def _merge_from_json(data: dict, project_id: int, chapter_num: int = 0) -> dict:
    """
    Применить структурированный JSON-анализ к State Engine.
    Надёжный путь: никаких regex по свободному тексту.
    """
    state = get_state(project_id)
    global_text = state.get("global_state", "")
    plot_text   = state.get("plot_matrix",  "")
    memory_text = state.get("memory_graph", "")

    fields_changed = []
    new_chars: list[str] = []

    def _record(field_name, before, after):
        if before != after and after and not str(after).startswith("["):
            fields_changed.append({"field": field_name, "before": before, "after": after})

    # ── Персонажи ──────────────────────────────────────────────────────────
    for char in data.get("global_state_changes", []):
        name = (char.get("name") or "").strip()
        if not name:
            continue

        char_exists = _find_char_block(global_text, name)

        if char_exists:
            # Применяем по полям
            for field_key, regex_key, json_key in [
                ("состояние", "СОСТОЯНИЕ",  "состояние"),
                ("локация",   "ЛОКАЦИЯ",    "локация"),
                ("цель",      "ЦЕЛЬ_СЕЙЧАС","цель"),
            ]:
                val = (char.get(json_key) or "").strip()
                if _is_real_value(val):
                    global_text = _apply_existing_char(
                        name,
                        f"{field_key}: {val}",
                        global_text,
                        _record,
                    )
            # Поле "узнал" — дописываем к ЗНАЕТ
            uznal = (char.get("узнал") or "").strip()
            if _is_real_value(uznal):
                char_m = _find_char_block(global_text, name)
                if char_m:
                    block = char_m.group(2)
                    block = _apply_char_knows(uznal, block, name, _record)
                    global_text = global_text[:char_m.start(2)] + block + global_text[char_m.end(2):]
        else:
            # Новый персонаж — единственный шаблон через _create_char_entry
            state_val = (char.get("состояние") or "").strip()
            loc_val   = (char.get("локация")   or "").strip()
            goal_val  = (char.get("цель")       or "").strip()
            new_entry = _create_char_entry(name, state_val, loc_val, goal_val)

            if "## ПЕРСОНАЖИ" in global_text:
                global_text = global_text.replace("## ПЕРСОНАЖИ", "## ПЕРСОНАЖИ" + new_entry, 1)
            else:
                global_text += "\n" + new_entry
            new_chars.append(name)
            display_val = state_val if _is_real_value(state_val) else "добавлен"
            fields_changed.append({"field": f"{name} (новый персонаж)", "before": "", "after": display_val})

    # ── Сюжет ──────────────────────────────────────────────────────────────
    plot = data.get("plot_changes", {})
    next_step = (plot.get("следующий_шаг") or "").strip()
    if _is_real_value(next_step):
        plot_text = _apply_doc_field("след_шаг", "СЛЕДУЮЩИЙ_ШАГ", next_step,
                                     plot_text, "Сюжет.следующий_шаг", _record)

    status = (plot.get("статус") or "").strip()
    if _is_real_value(status):
        plot_text = _apply_doc_field("статус", "СТАТУС", status,
                                     plot_text, "Сюжет.статус", _record)

    # ── Мир ────────────────────────────────────────────────────────────────
    world_moment = (data.get("world_moment") or "").strip()
    if _is_real_value(world_moment):
        global_text = _apply_doc_field("момент", "МОМЕНТ", world_moment[:200],
                                       global_text, "Мир.момент", _record)

    # ── Память ─────────────────────────────────────────────────────────────
    for mem in data.get("memory_changes", []):
        name = (mem.get("name") or "").strip()
        knows_list = [k for k in (mem.get("knows") or []) if k and isinstance(k, str)]
        if not name or not knows_list:
            continue
        knows_val = "; ".join(knows_list)
        pattern = rf"(###\s*{re.escape(name)}\nЗНАЕТ:\s*)(.*?)(?=\nНЕ_ЗНАЕТ|###|\Z)"
        mem_m = re.search(pattern, memory_text, re.DOTALL | re.IGNORECASE)
        if mem_m:
            existing = mem_m.group(2).strip()
            new_knows = (existing.rstrip() + "\n" if existing and existing != "[]" else "") + \
                        "\n".join(f"- {k}" for k in knows_list)
            memory_text = memory_text[:mem_m.start(2)] + new_knows + memory_text[mem_m.end(2):]
            _record(f"Память.{name}", existing, new_knows)

    # ── Закрытые обещания ──────────────────────────────────────────────────
    resolved_ids = [
        pid for pid in data.get("resolved_promises", [])
        if pid and isinstance(pid, str)
    ]
    if resolved_ids:
        try:
            from .l3_memory import mark_promise_resolved
            for pid in resolved_ids:
                # resolved_chapter неизвестен здесь напрямую — mark_promise_resolved
                # обновляет саммари главы-источника (id "5_0" → глава 5).
                # Глава закрытия пишется как 0 — sentinel, означает "закрыто, глава неизвестна".
                # При необходимости можно передавать chapter_num через аргумент merge.
                mark_promise_resolved(project_id, pid, resolved_chapter=chapter_num)
                fields_changed.append({
                    "field":  f"promise.{pid}",
                    "before": "active",
                    "after":  "resolved",
                })
        except Exception as e:
            handle_error("_merge_from_json resolved_promises", e, level=ErrorLevel.RECOVERABLE)

    changed = bool(fields_changed)
    if changed:
        update_state(project_id, global_text, plot_text, memory_text)

    return {"changed": changed, "fields": fields_changed, "new_chars": new_chars}


def merge_analysis_into_state(
    project_id: int,
    raw_analysis: str,
    chapter_num: int = 0,
) -> dict:
    """
    Автоматически применить анализ главы к State Engine.

    Поддерживает два формата ответа LLM:
    1. JSON (новый)  — надёжный, никакого regex по свободному тексту
    2. Text (legacy) — regex-парсер для обратной совместимости

    chapter_num — номер главы которая закрывает обещания (для resolved_promises).

    Возвращает: {"changed": bool, "fields": [...], "new_chars": [...]}
    """
    # Пробуем JSON-формат
    import json as _json
    try:
        match = re.search(r'\{.*\}', raw_analysis, re.DOTALL)
        if match:
            data = _json.loads(match.group())
            # Базовая валидация: JSON-анализ должен иметь хотя бы один из ключевых полей
            if any(k in data for k in ("global_state_changes", "plot_changes",
                                       "memory_changes", "next_context",
                                       "resolved_promises")):
                return _merge_from_json(data, project_id, chapter_num)
    except Exception as e:
        handle_error(f"merge_analysis_into_state JSON parse ({project_id})", e,
                     level=ErrorLevel.RECOVERABLE)

    # Fallback: legacy regex-парсер (для старых сохранённых анализов)
    return _merge_from_legacy_text(project_id, raw_analysis)


def _merge_from_legacy_text(project_id: int, raw_analysis: str) -> dict:
    """Legacy regex-парсер для старых текстовых анализов (до JSON-формата)."""
    state = get_state(project_id)
    global_text = state.get("global_state", "")
    plot_text   = state.get("plot_matrix", "")
    memory_text = state.get("memory_graph", "")

    fields_changed = []
    new_chars = []

    def _record(field_name, before, after):
        if before != after and after and not after.startswith("["):
            fields_changed.append({"field": field_name, "before": before, "after": after})

    global_block_m = re.search(
        r"=== GLOBAL_STATE — ИЗМЕНЕНИЯ ===(.*?)(?====|$)", raw_analysis, re.DOTALL
    )
    if global_block_m:
        global_text = _apply_global_block(
            global_block_m.group(1), global_text, _record, new_chars
        )

    plot_block_m = re.search(
        r"=== PLOT_MATRIX — ИЗМЕНЕНИЯ ===(.*?)(?====|$)", raw_analysis, re.DOTALL
    )
    if plot_block_m:
        plot_text = _apply_plot_block(plot_block_m.group(1), plot_text, _record)

    changed = bool(fields_changed)
    if changed:
        update_state(project_id, global_text, plot_text, memory_text)

    return {"changed": changed, "fields": fields_changed, "new_chars": new_chars}


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


def extract_freeform_with_llm(freeform_text: str, api_call_fn) -> dict | None:
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

        # Чистим markdown обёртку
        clean = re.sub(r"```json|```", "", raw).strip()
        m = re.search(r"(\{.*\})", clean, re.DOTALL)
        if m:
            clean = m.group(1)
        data = json.loads(clean)

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


def parse_structured_state_smart(state: dict, api_call_fn=None) -> dict:
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
