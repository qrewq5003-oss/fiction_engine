"""
genre_mix.py — второй жанр проекта: смешение жанров и модификаторы.

Зачем. Жанр проекта один, а книги — нет: детектив с любовной линией,
городское фэнтези с расследованием, комедийный детектив, YA-фэнтези.
GENRE_MERGER.md предлагал собирать гибрид списком модулей вручную, в
коде; в интерфейсе смешения не было. Теперь у проекта есть второй слой.

Два вида второго слоя:
- жанр из 35 ключей — вторая линия книги. Основной жанр задаёт структуру,
  темп, контракт, арку и финал; второй добавляет свои обещания читателю
  и 2–3 модуля, а жанровые варианты модулей остаются для обоих семейств;
- модификатор — тон или аудитория поверх любого жанра: комедия, young
  adult. Их профили в базе (comedic.md, young_adult.md) прямо пишут
  «любой жанр»: это не жанры, и ключей у них нет.

Второй слой не выбран — блок движка не меняется ни на символ.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .engine_config import GENRE_KEYWORDS, GENRE_MODULES

SECONDARY_HEADER = "[ВТОРОЙ ЖАНР"

# Модификатор: название, профиль в profiles/GENRE/, модули базы
MODIFIERS: dict[str, dict] = {
    "comedy": {
        "label": "Комедия",
        "profile": "comedic.md",
        "modules": ["15_dialogue_style", "11_micromoments_library"],
    },
    "young_adult": {
        "label": "Подростковая проза (YA)",
        "profile": "young_adult.md",
        "modules": ["09_deep_character_psychology", "16_pov_filters"],
    },
}

# Разделы профиля модификатора, которые идут в промпт. Архетипы, динамика
# и диалог с примером — нет: пример реплики модель переносит в текст.
_MODIFIER_SECTIONS = ("СУТЬ", "ОБЯЗАТЕЛЬНЫЕ ХАРАКТЕРИСТИКИ", "ТИПИЧНЫЕ ОШИБКИ")

# Сколько модулей второго жанра добавлять: больше — и он перетягивает книгу
SECONDARY_GENRE_MODULES = 2


def is_secondary_key(key: str | None) -> bool:
    return bool(key) and (key in MODIFIERS or key in GENRE_KEYWORDS)


def project_secondary_key(project: dict | None) -> str | None:
    key = (project or {}).get("genre_secondary")
    return key if is_secondary_key(key) else None


def secondary_modules(key: str | None) -> list[str]:
    if not key:
        return []
    if key in MODIFIERS:
        return list(MODIFIERS[key]["modules"])
    return list(GENRE_MODULES.get(key, []))[:SECONDARY_GENRE_MODULES]


def _engine_path() -> Path:
    # Через модуль: трассировка манифеста и тесты подменяют get_engine_path
    from . import engine_loaders
    return engine_loaders.get_engine_path()


def _catalog(key: str) -> dict:
    p = _engine_path() / "04_GENRE_ENGINE" / "catalog" / f"{key}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def secondary_label(key: str | None) -> str:
    if not key:
        return ""
    if key in MODIFIERS:
        return MODIFIERS[key]["label"]
    return _catalog(key).get("display_name", key)


def secondary_options() -> list[dict]:
    """Для выбора: сначала модификаторы, потом жанры. [{key, label, group}]"""
    out = [{"key": k, "label": v["label"], "group": "Тон и аудитория"}
           for k, v in MODIFIERS.items()]
    from .unified_engine import get_all_genre_options
    out += [{"key": o["key"], "label": o["label"], "group": "Жанры"}
            for o in get_all_genre_options()]
    return out


def _contract_promises(key: str) -> list[str]:
    """Строки «Обязательно» из раздела контракта поджанра."""
    from .engine_loaders_genre import load_genre_contract
    lines: list[str] = []
    inside = False
    for raw in load_genre_contract(_engine_path(), key).split("\n"):
        line = raw.strip()
        if line.startswith("### "):
            inside = line[4:].upper().startswith("ОБЯЗАТЕЛЬНО")
            continue
        if line.startswith("## ") and lines:
            break
        if inside and line and line != "---":
            lines.append(line)
    return lines[:4]


def _modifier_body(key: str) -> list[str]:
    p = _engine_path() / "05_CHARACTER_ENGINE" / "profiles" / "GENRE" / MODIFIERS[key]["profile"]
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[str] = []
    for title, body in re.findall(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        if not any(title.upper().startswith(s) for s in _MODIFIER_SECTIONS):
            continue
        for raw in body.split("\n"):
            line = raw.strip().replace("**", "")
            if not line or line == "---" or line.startswith("#"):
                continue
            if title.upper().startswith("ТИПИЧНЫЕ ОШИБКИ"):
                line = "Избегай: " + line.lstrip("- ")
            out.append(line if line.startswith("- ") else f"- {line}")
    return out


def load_secondary_section(primary_key: str | None, key: str | None) -> str:
    """Раздел «Второй жанр» для блока движка. Пусто — второго слоя нет."""
    if not is_secondary_key(key) or key == primary_key:
        return ""
    label = secondary_label(key)
    if key in MODIFIERS:
        body = _modifier_body(key or "")
        if not body:
            return ""
        return (f"{SECONDARY_HEADER}: {label}]\n"
                f"Тон и аудитория поверх основного жанра. Жанр задаёт сюжет, "
                f"структуру и финал; это — как он звучит и для кого.\n" + "\n".join(body))
    promises = _contract_promises(key or "")
    elements = _catalog(key or "").get("key_elements", [])
    if not promises and not elements:
        return ""
    parts = [f"{SECONDARY_HEADER}: {label}]",
             "Вторая линия книги. Основной жанр задаёт структуру, темп, арку и финал; "
             "второй вплетается в них — его обещания читатель тоже ждёт, но они "
             "не отменяют обещаний основного."]
    if promises:
        parts.append("Обещания второго жанра:\n" + "\n".join(f"- {p}" for p in promises))
    # Каталог — только если контракт скуп: иначе он его повторяет
    if elements and len(promises) < 2:
        parts.append("Что в нём должно быть: " + "; ".join(elements[:5]) + ".")
    return "\n".join(parts)
