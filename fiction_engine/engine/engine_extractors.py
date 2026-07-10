"""
engine_extractors.py — утилиты извлечения текста из markdown-модулей.

Ответственность: читать сырой текст модуля и возвращать только
практически ценную часть — без метаданных, кодовых блоков и балласта.

Не знает ничего о жанрах, путях, проектах.
Входные данные — строки. Выходные данные — строки.
"""

from .engine_config import _COMPILED_PATTERNS, _SKIP_PATTERNS


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


def _extract_module_essence(content: str, max_lines: int) -> str:
    """
    Умный экстрактор: возвращает суть модуля без метаданных и кодовых блоков.

    Стратегия (MINI first для всех режимов):
    - quick  (max_lines <= 35): только MINI если есть; иначе начало файла
    - quality/master (max_lines > 35): MINI как база + тело до max_lines
      Решает проблему модулей где начало — архитектурное описание,
      а рабочий контент (примеры, правила, запреты) — в середине/конце.
    """
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
