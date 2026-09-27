"""
engine_extractors.py — утилиты извлечения текста из markdown-модулей.

Ответственность: читать сырой текст модуля и возвращать только
практически ценную часть — без метаданных, кодовых блоков и балласта.

Не знает ничего о жанрах, путях, проектах.
Входные данные — строки. Выходные данные — строки.
"""

import re

from .engine_config import (_COMPILED_PATTERNS, _SKIP_PATTERNS,
                            GENRE_VARIANT_LABELS, META_SECTION_WORDS)


def _is_valuable(line: str) -> bool:
    """Строка несёт практическую ценность (правило, пример, запрет)."""
    s = line.strip()
    if not s:
        return False
    for p in _SKIP_PATTERNS:
        if p.match(s):
            return False
    for p in _COMPILED_PATTERNS:
        if p.search(s):
            return True
    return False


def _extract_mini_section(content: str) -> str:
    """
    Извлечь секцию ## MINI из модуля если она есть.
    MINI-секции содержат суть модуля в 10-20 строках для quick режима.
    """
    for marker in ["## ## MINI", "## MINI"]:
        idx = content.find(marker)
        if idx >= 0:
            chunk = content[idx:]
            lines = chunk.split("\n")
            result = []
            in_code = False
            for line in lines[1:]:
                stripped = line.strip()
                if stripped.startswith("```"):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                # Граница секции: следующий заголовок того же уровня.
                # Без этого MINI забирала всё до конца файла — в реальных
                # модулях MINI стоит последней, поэтому дефект не проявлялся,
                # но стоит добавить секцию после неё, и «суть модуля в 10-20
                # строках» превращается в весь остаток файла, а max_lines
                # для quick-режима перестаёт что-либо ограничивать.
                if stripped.startswith("## ") and "MINI" not in stripped:
                    break
                if any(p.match(stripped) for p in _SKIP_PATTERNS):
                    continue
                result.append(line)
            return "\n".join(result).strip()
    return ""


def _extract_body_lines(content: str, max_lines: int) -> str:
    """
    Извлечь содержательные строки из тела модуля (после первого ## заголовка),
    пропуская MINI-секцию, метаданные и кодовые блоки.
    Используется как дополнение к MINI в quality/master режимах.
    """
    lines = content.split("\n")
    result = []
    in_code_block = False
    skip_header = True
    in_mini = False
    last_was_empty = False

    for line in lines:
        stripped = line.strip()

        if skip_header:
            if stripped.startswith("## "):
                skip_header = False
            else:
                continue

        # Пропускаем MINI-секцию целиком — она уже добавлена отдельно
        if "## MINI" in stripped or "## ## MINI" in stripped:
            in_mini = True
            continue
        if in_mini:
            # Выходим из MINI при начале следующего ## раздела
            if stripped.startswith("## "):
                in_mini = False
            else:
                continue

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        if any(p.match(stripped) for p in _SKIP_PATTERNS):
            continue

        if not stripped:
            if last_was_empty:
                continue
            last_was_empty = True
        else:
            last_was_empty = False

        result.append(line)
        if len(result) >= max_lines:
            break

    return "\n".join(result).strip()


def _is_meta_heading(line: str) -> bool:
    s = line.strip()
    return s.startswith("## ") and any(w in s.upper() for w in META_SECTION_WORDS)


def _strip_meta_sections(content: str) -> str:
    """Убрать разделы «## НАЗНАЧЕНИЕ», «## ИНТЕГРАЦИЯ» и т. п. целиком."""
    out: list[str] = []
    skipping = False
    for line in content.split("\n"):
        if line.strip().startswith("## "):
            skipping = _is_meta_heading(line)
        if not skipping:
            out.append(line)
    return "\n".join(out)


def _heading_level(line: str) -> int | None:
    """Уровень заголовка: число «#»; жирная метка «**…:**» — ниже любого."""
    s = line.strip()
    if s.startswith("#"):
        return len(s) - len(s.lstrip("#"))
    if s.startswith("**") and s.endswith(":**"):
        return 7
    return None


def drop_empty_headings(text: str) -> str:
    """
    Убрать заголовки, под которыми ничего нет.

    Такие заголовки остаются, когда содержимое раздела лежало в код-блоке
    и экстрактор его выбросил: «**Формула усталости:**» — и пусто. В
    промпте они только шум. Удаление повторяется, пока есть что удалять:
    раздел, у которого пропали все подразделы, тоже становится пустым.
    """
    lines = text.split("\n")
    while True:
        empty = set()
        for i, line in enumerate(lines):
            level = _heading_level(line)
            if level is None:
                continue
            has_text = False
            for nxt in lines[i + 1:]:
                nxt_level = _heading_level(nxt)
                if nxt_level is not None and nxt_level <= level:
                    break
                s = nxt.strip()
                if nxt_level is None and s and s != "---":
                    has_text = True
                    break
            if not has_text:
                empty.add(i)
        if not empty:
            break
        lines = [l for i, l in enumerate(lines) if i not in empty]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


_VARIANT_RE = re.compile(r"^\*\*([^*]+):\*\*")
_ALL_VARIANT_LABELS = frozenset().union(*GENRE_VARIANT_LABELS.values())


def filter_genre_variants(text: str, genre_key: str | None) -> str:
    """
    Оставить из жанровых вариантов («**ХОРРОР:** …») только свой жанр.

    Жанр не определён — оставить все: универсальный промпт вправе видеть
    каждый вариант.
    """
    if not genre_key:
        return text
    own = GENRE_VARIANT_LABELS.get(genre_key.split("_")[0])
    if own is None:
        return text
    out = []
    for line in text.split("\n"):
        m = _VARIANT_RE.match(line.strip())
        if m:
            parts = {p.strip() for p in m.group(1).split("/")}
            if parts & _ALL_VARIANT_LABELS and not parts & own:
                continue
        out.append(line)
    return "\n".join(out)


def _extract_module_essence(content: str, max_lines: int) -> str:
    """
    Умный экстрактор: возвращает суть модуля без метаданных и кодовых блоков.

    Стратегия (MINI first для всех режимов):
    - quick  (max_lines <= 35): только MINI если есть; иначе начало файла
    - quality/master (max_lines > 35): MINI как база + тело до max_lines
      Решает проблему модулей где начало — архитектурное описание,
      а рабочий контент (примеры, правила, запреты) — в середине/конце.

    Служебные разделы (НАЗНАЧЕНИЕ, ИНТЕГРАЦИЯ…) вырезаются до разбора:
    раньше добор тела после MINI начинался именно с них.
    """
    content = _strip_meta_sections(content)
    mini = _extract_mini_section(content)

    if max_lines <= 35:
        # quick: только MINI если достаточно содержательная
        if mini and len(mini.split("\n")) >= 5:
            return mini
    else:
        # quality/master: MINI + дополнение из тела файла
        if mini and len(mini.split("\n")) >= 5:
            mini_lines = mini.split("\n")
            remaining = max_lines - len(mini_lines)
            if remaining <= 5:
                return mini
            body = _extract_body_lines(content, max_lines=remaining)
            if body:
                return mini + "\n\n" + body
            return mini

    lines = content.split("\n")
    result = []
    in_code_block = False
    skip_header = True
    last_was_empty = False

    for line in lines:
        stripped = line.strip()

        if skip_header:
            if stripped.startswith("## "):
                skip_header = False
            else:
                continue

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        if any(p.match(stripped) for p in _SKIP_PATTERNS):
            continue

        if not stripped:
            if last_was_empty:
                continue
            last_was_empty = True
        else:
            last_was_empty = False

        result.append(line)
        if len(result) >= max_lines:
            break

    return "\n".join(result).strip()
