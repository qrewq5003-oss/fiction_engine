"""
engine_extractors.py — утилиты извлечения текста из markdown-модулей.

Ответственность: читать сырой текст модуля и возвращать только
практически ценную часть — без метаданных, кодовых блоков и балласта.

Не знает ничего о жанрах, путях, проектах.
Входные данные — строки. Выходные данные — строки.
"""

import re

from .engine_config import GENRE_VARIANT_LABELS, META_SECTION_WORDS


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


def filter_genre_variants(text: str, genre_key: str | None,
                          also: str | None = None,
                          extra: frozenset = frozenset()) -> str:
    """
    Оставить из жанровых вариантов («**ХОРРОР:** …») только свой жанр.

    also — второй жанр проекта (genre_mix.py): его варианты тоже остаются,
    у «детектива + романтики» в модулях есть и детективные, и романтические
    подсказки. extra — метки, которые открывают тона (жуть → ХОРРОР,
    романтика → РОМАНТИКА; genre_mix.layer_variant_labels).

    Жанр не определён — оставить все: универсальный промпт вправе видеть
    каждый вариант.
    """
    if not genre_key:
        return text
    own = GENRE_VARIANT_LABELS.get(genre_key.split("_")[0])
    if own is None:
        return text
    own = own | GENRE_VARIANT_LABELS.get((also or "").split("_")[0], frozenset()) | extra
    out = []
    for line in text.split("\n"):
        m = _VARIANT_RE.match(line.strip())
        if m:
            parts = {p.strip() for p in m.group(1).split("/")}
            if parts & _ALL_VARIANT_LABELS and not parts & own:
                continue
        out.append(line)
    return "\n".join(out)


PROMPT_QUICK = "## PROMPT:QUICK"
PROMPT_FULL = "## PROMPT:FULL"


def _section(content: str, heading: str) -> str:
    """Текст раздела «## …» до следующего «## », без самого заголовка."""
    idx = content.find(heading)
    if idx < 0:
        return ""
    body = content[idx + len(heading):].split("\n", 1)
    rest = body[1] if len(body) > 1 else ""
    end = rest.find("\n## ")
    text = rest if end < 0 else rest[:end]
    # Комментарии <!-- … --> — пометки для автора, модели они не нужны;
    # разделитель «---» в конце — граница раздела, а не текст
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()
    while text.endswith("---"):
        text = text[:-3].rstrip()
    return text


def extract_prompt_sections(content: str, full: bool) -> str | None:
    """
    Явные секции для промпта, если автор модуля их написал.

    PROMPT:QUICK — ядро, идёт во всех режимах. PROMPT:FULL — дополнение
    для QUALITY/MASTER, идёт после ядра. Эти секции пишутся для модели,
    а не для человека: без код-блоков и описания «системы». Их нет —
    None, и работает прежний разбор MINI + тело (AUDIT_UNIFIED.md, 4б).
    """
    quick = _section(content, PROMPT_QUICK)
    if not quick:
        return None
    if not full:
        return quick
    extra = _section(content, PROMPT_FULL)
    return f"{quick}\n\n{extra}" if extra else quick


def _extract_module_essence(content: str, max_lines: int) -> str:
    """
    Суть модуля для промпта: секции PROMPT:QUICK, а при max_lines > 35
    (QUALITY и MASTER) — ещё PROMPT:FULL. Размер секций задаёт автор,
    лимит строк к ним не применяется: обрезка по строкам и породила
    пустые заголовки (U3).

    Модуля без секций нет: все 25 модулей их имеют, и это требует
    tests/test_unified_contract.py. Прежний разбор MINI и тела файла
    убран — его ветка больше не выполнялась. Нет секций — пустая строка,
    а отметку о пропавшем модуле делает load_module.
    """
    return extract_prompt_sections(content, full=max_lines > 35) or ""
