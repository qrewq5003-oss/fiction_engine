"""
style_profiles.py — стиль серии: выбор в проекте и раздел блока движка.

Зачем. В базе 12 стилевых профилей (05_CHARACTER_ENGINE/profiles/STYLE/):
кинематографичный, литературный, нуар, минимализм… Движок их не читал —
AUDIT_UNIFIED.md, «Справочные файлы»: подключить как выбор в проекте
рядом с жанром. Жанр отвечает на вопрос «что за история», стиль — «как
она рассказана»: один и тот же детектив можно писать коротко и жёстко
или медленно и плотно.

Что идёт в промпт. Суть, характеристики и правило профиля. Не идут:
- примеры — модель переносит их в текст (так же решено для пресетов
  голоса). Пример «Литературного» к тому же построен на сравнении
  «как знают о больном зубе» — ровно на приёме, который ai_cliches.md
  теперь называет штампом;
- «Подходит для» — это подсказка автору при выборе, а не указание
  модели; она показывается в интерфейсе.

Стиль не выбран — блок движка не меняется ни на символ.
"""

from __future__ import annotations

import re
from pathlib import Path

STYLE_SUBDIR = Path("05_CHARACTER_ENGINE") / "profiles" / "STYLE"

# Названия для интерфейса. Заголовки файлов частью английские
# («Dialogue Focused»), а выбирает стиль автор, пишущий по-русски.
STYLE_LABELS = {
    "atmospheric":        "Атмосферный",
    "cinematic":          "Кинематографичный",
    "commercial":         "Коммерческий",
    "dialogue_focused":   "Через диалог",
    "emotional_depth":    "Эмоциональная глубина",
    "epic_voice":         "Эпический голос",
    "first_person_close": "Первое лицо, вплотную",
    "literary":           "Литературный",
    "modern_minimal":     "Минимализм",
    "noir_style":         "Нуар",
    "omniscient":         "Всеведущий рассказчик",
    "tight_thriller":     "Сжатый триллер",
}

STYLE_HEADER = "[СТИЛЬ СЕРИИ"

# Разделы профиля, которые в промпт не идут
_SKIP_SECTIONS = ("ПРИМЕР", "ПОДХОДИТ ДЛЯ", "НЕ ПОДХОДИТ ДЛЯ")
_SUITS = re.compile(r"^\*{0,2}Подходит для:?\*{0,2}\s*(.+)$", re.I)


def _style_dir() -> Path:
    # Через модуль, а не импортом имени: трассировка манифеста и тесты
    # подменяют engine_loaders.get_engine_path
    from . import engine_loaders
    return engine_loaders.get_engine_path() / STYLE_SUBDIR


def _read(key: str) -> str:
    p = _style_dir() / f"{key}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _suits(content: str) -> str:
    """Для каких жанров профиль: строка «Подходит для: …» или раздел."""
    lines = content.split("\n")
    for i, raw in enumerate(lines):
        line = raw.strip()
        m = _SUITS.match(line)
        if m:
            return m.group(1).strip().rstrip(".")
        if line.lstrip("# ").upper() == "ПОДХОДИТ ДЛЯ":
            body = [x.strip() for x in lines[i + 1:] if x.strip() and not x.startswith("---")]
            return body[0].rstrip(".") if body else ""
    return ""


def list_style_profiles() -> list[dict]:
    """Профили для выбора: [{key, label, suits}], в порядке STYLE_LABELS."""
    out = []
    for key, label in STYLE_LABELS.items():
        content = _read(key)
        if content:
            out.append({"key": key, "label": label, "suits": _suits(content)})
    return out


def is_style_key(key: str | None) -> bool:
    return bool(key) and key in STYLE_LABELS


def load_style_profile(key: str | None) -> str:
    """Раздел «Стиль серии» для блока движка. Пусто — стиль не выбран."""
    if not is_style_key(key):
        return ""
    content = _read(key or "")
    if not content:
        return ""
    lines: list[str] = []
    skipping = False
    for raw in content.split("\n"):
        line = raw.strip()
        if line.startswith("# "):                 # заголовок файла
            continue
        if line.startswith("## "):
            skipping = any(w in line.upper() for w in _SKIP_SECTIONS)
            continue
        if skipping or not line or line == "---" or _SUITS.match(line):
            continue
        line = re.sub(r"^\*\*Суть:\*\*\s*|^Суть:\s*", "", line)
        lines.append(line if line.startswith("- ") else f"- {line}")
    if not lines:
        return ""
    return (f"{STYLE_HEADER}: {STYLE_LABELS[key or '']}]\n"
            f"Как рассказана вся серия. Держи этот стиль в каждой сцене; "
            f"жанровые правила выше говорят что, стиль — как.\n" + "\n".join(lines))


def project_style_key(project: dict | None) -> str | None:
    key = (project or {}).get("style_key")
    return key if is_style_key(key) else None
