"""
state_merge.py — слияние анализа главы в State Engine.

Анализ главы (state.analyze_chapter) приходит JSON-ом — или старым текстом с
разделами «=== GLOBAL_STATE — ИЗМЕНЕНИЯ ===». merge_analysis_into_state
применяет его к трём документам State: global_state (персонажи, мир),
plot_matrix (сюжет, детали серии), memory_graph (кто что знает).

Вынесено из db_state.py (13.10): там было хранение, разбор и слияние в одном
файле на 935 строк, а слияние — самая хрупкая часть: терпимый поиск полей в
тексте, который пишут и модель, и автор.
"""

import re
from typing import Callable, Optional

from .error_policy import handle_error, ErrorLevel

# record_fn(поле, было, стало) — записать изменение для показа автору
RecordFn = Callable[[str, str, str], None]


# ─── Слияние анализа в State ──────────────────────────────────────────────────

def _is_real_value(val: str) -> bool:
    """Значение не пустое, не плейсхолдер и не 'без изменений'."""
    return bool(val) and not val.startswith("[") and "без изменений" not in val.lower()


# ─── Терпимый разбор полей State Engine ───────────────────────────────────────
#
# В проекте исторически сосуществуют три написания одних и тех же полей:
#   • db_core._default_global()            → СОСТОЯНИЕ: ЛОКАЦИЯ: ЦЕЛЬ_СЕЙЧАС: ЗНАЕТ:
#   • _archive/08_STATE_ENGINE/global_state_template.md → Состояние: Локация: Цель текущая: Знает:
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
    "где":       ["ГДЕ_СЕЙЧАС", "Где сейчас", "ГДЕ СЕЙЧАС"],
}


def _field_pattern(alias: str) -> str:
    """
    Регексп строки поля: отступ, написание ключа, значение, хвостовой CR.

    Группа 4 (\r) отделена специально: файлы State, пришедшие из Windows,
    хранятся в CRLF, и без этого значение поля забирало бы \r внутрь,
    а перезапись строки ломала бы единообразие переводов строк.
    """
    return rf"^([ \t]*)({re.escape(alias)})[ \t]*:[ \t]*([^\r\n]*)(\r?)$"


def _find_field(text: str, field_key: str, fallback_key: str = "") -> Optional[re.Match[str]]:
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
                      record_fn: RecordFn) -> str:
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
    # (?!\w), а не \b: после «)» в «Митяй (Дмитрий Рябов)» границы слова нет,
    # персонаж не находился и дописывался дублем (книга на Sonnet 18.10, гл.3)
    n = re.escape(name) + r"(?!\w)"
    header = (
        rf"(?:^#{{2,4}}[ \t]*{n}[^\r\n]*$"
        rf"|^\[[ \t]*{n}[^\]\r\n]*\][ \t\r]*$"
        rf"|^\*\*[ \t]*{n}[^*\r\n]*\*\*[ \t\r]*$)"
    )
    return rf"({header}\n)((?:(?!{_HEADER_ANY}).*\n?)*)"


def _find_char_block(global_text: str, name: str) -> Optional[re.Match[str]]:
    """Найти блок персонажа по имени в любом из форматов заголовка."""
    if not name:
        return None
    return re.search(_char_block_pattern(name), global_text,
                     re.IGNORECASE | re.MULTILINE)


def _apply_doc_field(field_key: str, fallback_key: str, new_val: str,
                     text: str, record_name: str, record_fn: RecordFn) -> str:
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


def _apply_char_knows(knows_val: str, char_block: str, char_name: str,
                      record_fn: RecordFn) -> str:
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


def _apply_existing_char(name: str, section: str, global_text: str,
                         record_fn: RecordFn) -> str:
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


def _add_new_char(name: str, section: str, global_text: str, record_fn: RecordFn,
                  new_chars: list) -> str:
    """Добавить нового персонажа в global_text."""
    fields = {
        "состояние": re.search(r"состояние:\s*(.+?)(?:\n|$)", section),
        "локация":   re.search(r"локация:\s*(.+?)(?:\n|$)", section),
        "цель":      re.search(r"цель:\s*(.+?)(?:\n|$)", section),
    }

    def _val(key: str) -> str:
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
                        record_fn: RecordFn, new_chars: list) -> str:
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

        # Тот же терпимый поиск, что и в JSON-пути: заголовки бывают
        # «### Имя», «[ИМЯ — РОЛЬ]» и «**Имя**». Раньше legacy-путь знал
        # только первый вид и на остальных форматах дописывал дубль.
        char_exists = _find_char_block(global_text, name)
        if char_exists:
            global_text = _apply_existing_char(name, section, global_text, record_fn)
        else:
            global_text = _add_new_char(name, section, global_text, record_fn, new_chars)

    return global_text


def _apply_plot_block(pblock: str, plot_text: str, record_fn: RecordFn) -> str:
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


class _Changes:
    """Что изменилось при слиянии: поля для показа автору и новые персонажи."""

    def __init__(self) -> None:
        self.fields: list[dict] = []
        self.new_chars: list[str] = []
        self.bible_conflicts: list[dict] = []

    def record(self, field_name: str, before: str, after: str) -> None:
        if before != after and after and not str(after).startswith("["):
            self.fields.append({"field": field_name, "before": before, "after": after})

    def add(self, field_name: str, before: str, after: str) -> None:
        self.fields.append({"field": field_name, "before": before, "after": after})


_TEMPLATE_CHAR = re.compile(r"^#{2,4}[ \t]*\[[^\]\n]*\][ \t]*\n((?:(?!#{2,4}[ \t]|---).*\n?)*)", re.M)


def drop_template_characters(global_text: str) -> str:
    """
    Убрать из State шаблонного персонажа «### [Имя]» из пустого State нового
    проекта, если у него не заполнено ни одно поле (только подсказки в
    скобках). Он оставался рядом с настоящими персонажами и уходил писателю в
    каждой главе (книга-прогон 17.10, все 12 глав).
    """
    def keep(m: re.Match) -> str:
        values = [ln.split(":", 1)[1].strip() for ln in m.group(1).splitlines() if ":" in ln]
        filled = [v for v in values if v and not (v.startswith("[") and v.endswith("]"))]
        return m.group(0) if filled else ""
    return re.sub(r"\n{3,}", "\n\n", _TEMPLATE_CHAR.sub(keep, global_text or ""))


def _merge_characters(changes_list: list, global_text: str, ch: _Changes) -> str:
    """Изменения персонажей: поля известных, ЗНАЕТ += «узнал», новые — запись целиком."""
    global_text = drop_template_characters(global_text)
    for char in changes_list:
        name = (char.get("name") or "").strip()
        if not name:
            continue
        if _find_char_block(global_text, name):
            for field_key, json_key in (("состояние", "состояние"), ("локация", "локация"),
                                        ("цель", "цель")):
                val = (char.get(json_key) or "").strip()
                if _is_real_value(val):
                    global_text = _apply_existing_char(name, f"{field_key}: {val}",
                                                       global_text, ch.record)
            # Поле "узнал" — дописываем к ЗНАЕТ
            uznal = (char.get("узнал") or "").strip()
            char_m = _find_char_block(global_text, name) if _is_real_value(uznal) else None
            if char_m:
                block = _apply_char_knows(uznal, char_m.group(2), name, ch.record)
                global_text = global_text[:char_m.start(2)] + block + global_text[char_m.end(2):]
            continue
        # Новый персонаж — единственный шаблон через _create_char_entry
        state_val = (char.get("состояние") or "").strip()
        new_entry = _create_char_entry(name, state_val, (char.get("локация") or "").strip(),
                                       (char.get("цель") or "").strip())
        if "## ПЕРСОНАЖИ" in global_text:
            global_text = global_text.replace("## ПЕРСОНАЖИ", "## ПЕРСОНАЖИ" + new_entry, 1)
        else:
            global_text += "\n" + new_entry
        ch.new_chars.append(name)
        ch.add(f"{name} (новый персонаж)", "", state_val if _is_real_value(state_val) else "добавлен")
    return global_text


def _merge_plot(plot: dict, plot_text: str, ch: _Changes) -> str:
    # ГДЕ_СЕЙЧАС раньше не обновлялся вовсе: у автора после глав 2 и 3 в
    # нём так и стояло «на подножке скорой» из главы 1, и писатель главы 4
    # получил бы его как нынешнее положение дел
    for json_key, field_key, regex_key, label in (
            ("где_сейчас", "где", "ГДЕ_СЕЙЧАС", "Сюжет.где_сейчас"),
            ("следующий_шаг", "след_шаг", "СЛЕДУЮЩИЙ_ШАГ", "Сюжет.следующий_шаг"),
            ("статус", "статус", "СТАТУС", "Сюжет.статус")):
        val = (plot.get(json_key) or "").strip()
        if _is_real_value(val):
            plot_text = _apply_doc_field(field_key, regex_key, val, plot_text, label, ch.record)
    return plot_text


# Раздел «кто что знает»: сколько последних знаний держать на персонажа, и
# заготовка шаблона, которую убирает первый настоящий раздел
MEMORY_KNOWS_MAX = 15
MEMORY_HEADER = "## КТО ЧТО ЗНАЕТ"
_MEMORY_PLACEHOLDER = re.compile(r"###\s*\[Имя\]\s*\nЗНАЕТ:\s*\[\]\s*\nНЕ_ЗНАЕТ:\s*\[\]\s*\n"
                                 r"(?:ДУМАЕТ_ЧТО_ЗНАЕТ:\s*\[\]\s*\n?)?")


def _merge_memory(memory_changes: list, memory_text: str, ch: _Changes) -> str:
    """
    ЗНАЕТ в memory_graph дополняется новыми знаниями персонажа. Раздела
    персонажа нет — он создаётся: раньше знания тогда отбрасывались, и
    «кто что знает» оставался шаблоном с «### [Имя]» (проект автора, 16.10).
    """
    for mem in memory_changes:
        if not isinstance(mem, dict):
            continue
        name = (mem.get("name") or "").strip()
        knows_list = [k.strip() for k in (mem.get("knows") or []) if k and isinstance(k, str) and k.strip()]
        if not name or not knows_list:
            continue
        pattern = rf"(###\s*{re.escape(name)}\s*\nЗНАЕТ:[ \t]*)(.*?)(?=\nНЕ_ЗНАЕТ|\n###|\n## |\Z)"
        mem_m = re.search(pattern, memory_text, re.DOTALL | re.IGNORECASE)
        if mem_m:
            existing = mem_m.group(2).strip()
            old = [l for l in existing.splitlines() if l.startswith("- ")]
            seen = {l[2:].strip().lower() for l in old}
            add = [f"- {k}" for k in knows_list if k.lower() not in seen]
            if not add:
                continue
            new_knows = "\n" + "\n".join((old + add)[-MEMORY_KNOWS_MAX:])
            memory_text = memory_text[:mem_m.start(2)] + new_knows + memory_text[mem_m.end(2):]
            ch.record(f"Память.{name}", existing, new_knows.strip())
            continue
        block = (f"### {name}\nЗНАЕТ:\n" + "\n".join(f"- {k}" for k in knows_list[-MEMORY_KNOWS_MAX:])
                 + "\nНЕ_ЗНАЕТ: []\n")
        memory_text = _MEMORY_PLACEHOLDER.sub("", memory_text or "", count=1)
        if MEMORY_HEADER in memory_text:
            at = memory_text.index(MEMORY_HEADER) + len(MEMORY_HEADER)
            rest = memory_text[at:].lstrip("\n")
            memory_text = memory_text[:at] + "\n\n" + block + ("\n" + rest if rest else "")
        else:
            memory_text = f"{MEMORY_HEADER}\n\n{block}\n{memory_text}".rstrip() + "\n"
        ch.record(f"Память.{name}", "", "\n".join(f"- {k}" for k in knows_list))
    return memory_text


# Разделы сюжета, которые анализ главы раньше заполнял, а слияние отбрасывало
OPEN_QUESTIONS_HEADER = "## ОТКРЫТЫЕ ВОПРОСЫ"
SIDE_LINES_HEADER = "## ВТОРОСТЕПЕННЫЕ ЛИНИИ"
SECTION_ITEMS_MAX = 12


def _section_items(text: str, header: str) -> list[str]:
    m = re.search(rf"{re.escape(header)}[ \t]*\n(.*?)(?=\n## |\Z)", text or "", re.S)
    return [l[2:].strip() for l in m.group(1).splitlines() if l.startswith("- ")] if m else []


def _set_section_items(text: str, header: str, items: list[str]) -> str:
    """Заменить список раздела на месте; раздела нет — дописать его в конец."""
    body = "\n".join(f"- {x}" for x in items)
    pat = re.compile(rf"({re.escape(header)}[ \t]*\n)(.*?)(?=\n## |\Z)", re.S)
    if pat.search(text or ""):
        return pat.sub(lambda m: m.group(1) + body + "\n", text, count=1)
    return (text or "").rstrip() + f"\n\n{header}\n{body}\n"


_CH_PREFIX = re.compile(r"^(?:гл\.\s*\d+:\s*)+", re.I)


def _strip_ch(s: str) -> str:
    """Без метки главы в начале: модель повторяет «гл.N:» за списком State,
    и в State выходило «гл.2: гл.2: …»."""
    return _CH_PREFIX.sub("", s.strip())


def _merge_open_questions(questions: list, plot_text: str, chapter_num: int, ch: _Changes) -> str:
    qs = [_strip_ch(q) for q in questions or [] if isinstance(q, str) and _is_real_value(_strip_ch(q))]
    if not qs:
        return plot_text
    old = _section_items(plot_text, OPEN_QUESTIONS_HEADER)
    known = {_strip_ch(x).lower() for x in old}
    new = [f"гл.{chapter_num}: {q}" if chapter_num else q for q in qs if q.lower() not in known]
    if not new:
        return plot_text
    ch.add("Открытые вопросы", "", "; ".join(qs))
    return _set_section_items(plot_text, OPEN_QUESTIONS_HEADER, (old + new)[-SECTION_ITEMS_MAX:])


def _merge_side_lines(plot: dict, plot_text: str, chapter_num: int, ch: _Changes) -> str:
    """Новые линии — в «ВТОРОСТЕПЕННЫЕ ЛИНИИ»; закрытые — помечаются там же."""
    new_lines = [x.strip() for x in plot.get("новые_линии") or [] if isinstance(x, str) and _is_real_value(x.strip())]
    closed = [x.strip() for x in plot.get("закрытые_линии") or [] if isinstance(x, str) and _is_real_value(x.strip())]
    if not new_lines and not closed:
        return plot_text
    items = _section_items(plot_text, SIDE_LINES_HEADER)
    base = lambda s: re.sub(r"\s*\((?:с гл\.|закрыта в гл\.)[^)]*\)\s*$", "", s).strip().lower()
    for x in new_lines:
        if all(base(i) != x.lower() for i in items):
            items.append(f"{x} (с гл.{chapter_num})" if chapter_num else x)
    for x in closed:
        for i, it in enumerate(items):
            if base(it) == x.lower() and "закрыта" not in it:
                items[i] = re.sub(r"\s*\(с гл\.[^)]*\)\s*$", "", it) + \
                    (f" (закрыта в гл.{chapter_num})" if chapter_num else " (закрыта)")
    open_ = [i for i in items if "закрыта" not in i]
    shut = [i for i in items if "закрыта" in i][-4:]       # закрытые — только последние
    items = (shut + open_)[-SECTION_ITEMS_MAX:]
    ch.add("Сюжетные линии", "", "; ".join([f"+{x}" for x in new_lines] + [f"−{x}" for x in closed]))
    return _set_section_items(plot_text, SIDE_LINES_HEADER, items)


def _merge_promises(resolved: list, project_id: int, chapter_num: int, ch: _Changes) -> None:
    """Закрытые обещания — в саммари L3 главы-источника (id «5_0» → глава 5)."""
    ids = [pid for pid in resolved if pid and isinstance(pid, str)]
    if not ids:
        return
    try:
        from .l3_memory import mark_promise_resolved
        for pid in ids:
            mark_promise_resolved(project_id, pid, resolved_chapter=chapter_num)
            ch.add(f"promise.{pid}", "active", "resolved")
    except Exception as e:
        handle_error("_merge_from_json resolved_promises", e, level=ErrorLevel.RECOVERABLE)


def _merge_details(details_raw: list, plot_text: str, chapter_num: int, ch: _Changes) -> str:
    details = [d.strip() for d in details_raw if isinstance(d, str) and _is_real_value(d.strip())]
    if not details:
        return plot_text
    new_plot = merge_series_details(plot_text, details, chapter_num)
    if new_plot != plot_text:
        ch.add("Детали серии", "", "; ".join(details))
    return new_plot


def _merge_bible(entries: list, project_id: int, chapter_num: int, ch: _Changes) -> None:
    """Факты главы — в библию серии (дописываются; противоречие не перезаписывает)."""
    try:
        from .series_bible import record
        got = record(project_id, entries, chapter_num)
    except Exception as err:
        handle_error("_merge_from_json bible", err, level=ErrorLevel.RECOVERABLE)
        return
    for e in got["added"]:
        ch.add(f"Библия: {e['name']} — {e['attr']}", "", e["value"])
    for e in got["changed"]:
        ch.add(f"Библия: {e['name']} — {e['attr']}", e["was"], f"{e['value']} ({e['changed']})")
    for e in got["conflicts"]:
        # Видно автору в списке изменений; в библию как текущее значение не идёт
        ch.add(f"⚠ Противоречие с библией: {e['name']} — {e['attr']}",
               f"{e['was']} (гл.{e['was_chapter']})", e["value"])
    ch.bible_conflicts += got["conflicts"]


def _merge_from_json(data: dict, project_id: int, chapter_num: int = 0) -> dict:
    """
    Применить структурированный JSON-анализ к State Engine.
    Надёжный путь: никаких regex по свободному тексту.
    """
    from .db_state import SNAPSHOT_BEFORE, SNAPSHOT_RECOMPUTE, get_state, update_state
    state = get_state(project_id)
    ch = _Changes()
    global_text = state.get("global_state", "")
    plot_text = state.get("plot_matrix", "")
    memory_text = state.get("memory_graph", "")
    # Глава из середины книги (после неё есть принятые): State — это конец
    # книги, его «сейчас» — где герои, что дальше, состояние и цели, открытые
    # вопросы, побочные линии — не откатываем к этой главе. Из неё — только её
    # факты: детали, библия, события, закрытые обещания (разбор 21.10: анализ
    # переписанной гл.12 ставил писателю гл.25 «ГДЕ_СЕЙЧАС» из гл.12)
    from .db_chapters import last_chapter_number
    last = last_chapter_number(project_id) if chapter_num else None
    middle = bool(chapter_num and last and chapter_num < last)
    if not middle:
        global_text = _merge_characters(data.get("global_state_changes", []), global_text, ch)
        world_moment = (data.get("world_moment") or "").strip()
        if _is_real_value(world_moment):
            global_text = _apply_doc_field("момент", "МОМЕНТ", world_moment[:200],
                                           global_text, "Мир.момент", ch.record)
        plot = data.get("plot_changes") or {}
        plot_text = _merge_plot(plot, plot_text, ch)
        plot_text = _merge_side_lines(plot if isinstance(plot, dict) else {}, plot_text, chapter_num, ch)
        plot_text = _merge_open_questions(data.get("open_questions") or [], plot_text, chapter_num, ch)
    memory_text = _merge_memory(data.get("memory_changes", []), memory_text, ch)
    _merge_promises(data.get("resolved_promises", []), project_id, chapter_num, ch)
    plot_text = _merge_details(data.get("details") or [], plot_text, chapter_num, ch)
    _merge_bible(data.get("bible") or [], project_id, chapter_num, ch)

    changed = bool(ch.fields)
    if changed:
        # Снимок с номером главы — по нему «Откатить главу» и State на момент
        # главы находят State до неё. Глава из середины — другой пометкой: её
        # снимок — конец книги, и «перед анализом» сбил бы откат последней главы
        reason = (f"{SNAPSHOT_RECOMPUTE if middle else SNAPSHOT_BEFORE}{chapter_num}"
                  if chapter_num else "")
        update_state(project_id, global_text, plot_text, memory_text, _snapshot_reason=reason)
    return {"changed": changed, "fields": ch.fields, "new_chars": ch.new_chars,
            "bible_conflicts": ch.bible_conflicts}


# ─── Детали серии ────────────────────────────────────────────────────────────
#
# Замер 11.10 (bench/ab-series-memory-2026-10-11.json): с памятью противоречий
# между главами вдвое меньше, но остаются мелкие детали — шуба с каракулевым
# воротником становится бобровой, ворота из подъёмных — ржавыми. В State их не
# было: анализ главы писал персонажей, линии и знания. Теперь он выписывает и
# детали, они копятся разделом «ДЕТАЛИ СЕРИИ» в plot_matrix и идут генератору
# следующих глав и проверке непрерывности.

SERIES_DETAILS_HEADER = "## ДЕТАЛИ СЕРИИ"
SERIES_DETAILS_MAX = 60


_DETAIL_CHAPTER = re.compile(r"^гл\.(\d+):")
_DETAILS_SECTION = rf"{re.escape(SERIES_DETAILS_HEADER)}\n(.*?)(?=\n## |\Z)"


def detail_chapter(line: str) -> int | None:
    m = _DETAIL_CHAPTER.match(line)
    return int(m.group(1)) if m else None


def series_details(plot_text: str, before_chapter: int | None = None) -> list[str]:
    """Строки раздела «ДЕТАЛИ СЕРИИ» («гл.N: деталь»), по порядку добавления.

    before_chapter — только детали глав раньше этой. Писатель главы 1 получал
    детали глав 1–2 прошлой версии книги («красный источник: четыре, три, две
    с половиной секунды») и вставлял их в главу как предвидение. Строки без
    номера главы (записаны автором) идут всегда.
    """
    m = re.search(_DETAILS_SECTION, plot_text or "", re.S)
    if not m:
        return []
    out = [l[2:].strip() for l in m.group(1).splitlines() if l.startswith("- ")]
    if before_chapter is None:
        return out
    return [d for d in out if (detail_chapter(d) or 0) < before_chapter]


def detail_chapters(plot_text: str) -> set[int]:
    """Номера глав, у которых есть детали в разделе."""
    return {n for n in map(detail_chapter, series_details(plot_text)) if n}


def drop_series_details(plot_text: str, chapters: set[int]) -> str:
    """Убрать из раздела детали этих глав (глава удалена). Остальной текст — как был."""
    m = re.search(_DETAILS_SECTION, plot_text or "", re.S)
    if not m:
        return plot_text
    kept = [l for l in m.group(1).splitlines()
            if not (l.startswith("- ") and detail_chapter(l[2:].strip()) in chapters)]
    return plot_text[:m.start(1)] + "\n".join(kept) + plot_text[m.end(1):]


def merge_series_details(plot_text: str, details: list[str], chapter_num: int) -> str:
    """Добавить детали главы в раздел, без повторов, не больше SERIES_DETAILS_MAX строк."""
    old = series_details(plot_text)
    known = {_strip_ch(x).lower() for x in old}
    details = [_strip_ch(d) for d in details]
    new = [f"гл.{chapter_num}: {d}" if chapter_num else d
           for d in details if d and d.lower() not in known]
    if not new:
        return plot_text
    lines = (old + new)[-SERIES_DETAILS_MAX:]
    block = SERIES_DETAILS_HEADER + "\n" + "\n".join(f"- {x}" for x in lines)
    base = re.sub(rf"\n*{re.escape(SERIES_DETAILS_HEADER)}\n.*?(?=\n## |\Z)", "",
                  plot_text or "", flags=re.S).rstrip()
    return (base + "\n\n" + block).lstrip() + "\n"


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
    from .pipeline_llm import parse_json
    try:
        data = parse_json(raw_analysis)
        if isinstance(data, dict):
            # Базовая валидация: JSON-анализ должен иметь хотя бы один из ключевых полей
            if any(k in data for k in ("global_state_changes", "plot_changes", "details", "bible",
                                       "memory_changes", "next_context",
                                       "resolved_promises")):
                return _merge_from_json(data, project_id, chapter_num)
    except Exception as e:
        handle_error(f"merge_analysis_into_state JSON parse ({project_id})", e,
                     level=ErrorLevel.RECOVERABLE)

    # Ответ — JSON, но не разобран: старый текстовый разбор его не поймёт, и
    # анализ терялся молча — «применён», а State прежний (1 из 89 анализов
    # книг автора, гл.1 дымовой книги 19.10). Ошибка, а не «без изменений»
    if (raw_analysis or "").lstrip().lstrip("`").lstrip("json").lstrip().startswith("{"):
        err = "анализ главы не разобран (битый JSON) — State не обновлён"
        handle_error(f"merge_analysis_into_state ({project_id}, гл.{chapter_num})", ValueError(err),
                     level=ErrorLevel.DEGRADED)
        return {"changed": False, "fields": [], "new_chars": [], "bible_conflicts": [], "error": err}

    # Fallback: legacy regex-парсер (для старых сохранённых анализов)
    return _merge_from_legacy_text(project_id, raw_analysis)


def _merge_from_legacy_text(project_id: int, raw_analysis: str) -> dict:
    """Legacy regex-парсер для старых текстовых анализов (до JSON-формата)."""
    from .db_state import get_state, update_state
    state = get_state(project_id)
    global_text = state.get("global_state", "")
    plot_text   = state.get("plot_matrix", "")
    memory_text = state.get("memory_graph", "")

    fields_changed = []
    new_chars: list[str] = []

    def _record(field_name: str, before: str, after: str) -> None:
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
