"""
engine_loaders_genre.py — загрузчики жанровых блоков движка.

Ответственность: жанровый каталог, контракты, промпты, профили персонажей,
арки, специфика поджанра — всё что зависит от genre_key.
"""

import json
import re
from pathlib import Path
from .engine_config import (
    CONTRACT_MAP, SUBGENRE_CONTRACT_LABELS,
    CHAR_FULL_KEY_MAP, CHAR_FAMILY_FALLBACK, ANTAGONIST_GENRE_MAP,
)


def load_genre_catalog(engine_path: Path, genre_key: str) -> str:
    p = engine_path / "04_GENRE_ENGINE" / "catalog" / f"{genre_key}.json"
    if not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        parts = [f"ЖАНР: {data.get('display_name', genre_key)}"]
        if data.get("tone"):
            parts.append(f"Тональность: {data['tone']}")
        if data.get("key_elements"):
            parts.append(f"Ключевые элементы: {', '.join(data['key_elements'])}")
        if data.get("mistakes"):
            parts.append(f"ОШИБКИ ЖАНРА — избегать: {', '.join(data['mistakes'])}")
        if data.get("magic"):
            parts.append(f"Магия/Механика: {data['magic']}")
        if data.get("character_arcs"):
            parts.append(f"Арки: {data['character_arcs']}")
        return "\n".join(parts)
    except Exception:
        return ""


# _CONTRACT_MAP → импортируется из engine_config.CONTRACT_MAP

# _SUBGENRE_CONTRACT_LABELS → импортируется из engine_config.SUBGENRE_CONTRACT_LABELS


def load_genre_contract(engine_path: Path, genre_key: str) -> str:
    """Загрузить читательский контракт жанра."""
    genre_family = genre_key.split("_")[0]
    fname = CONTRACT_MAP.get(genre_family)
    if not fname:
        return ""
    p = engine_path / "16_GENRE_CONTRACT" / fname
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8")
    target = SUBGENRE_CONTRACT_LABELS.get(genre_key, "")

    lines = content.split("\n")
    result = []
    in_section = False
    for line in lines:
        if line.startswith("## "):
            if target and target.upper() in line.upper():
                in_section = True
            elif in_section:
                break
        if in_section or (not target and line.strip()):
            result.append(line)
        if len(result) >= 30:
            break

    if not result:
        result = [l for l in lines if l.strip()][:25]

    return "ЧИТАТЕЛЬСКИЙ КОНТРАКТ ЖАНРА:\n" + "\n".join(result)


def load_arc_hint(engine_path: Path, genre_key: str) -> str:
    """Загрузить жанровый шаблон арки из 12_ARCS."""
    genre_family = genre_key.split("_")[0] if genre_key else ""

    if genre_family == "fantasy":
        return _load_fantasy_arc(engine_path)

    heading_map = {
        "detective": "ДЕТЕКТИВ",
        "thriller":  "ТРИЛЛЕР",
        "horror":    "ХОРРОР",
        "scifi":     "НФ",
        "romance":   "РОМАНТИКА",
        "realism":   "УНИВЕРСАЛЬНЫЕ",
    }
    heading = heading_map.get(genre_family, "")
    if not heading:
        return ""
    return _load_arc_by_heading(engine_path, heading)


def _load_fantasy_arc(engine_path: Path) -> str:
    p = engine_path / "12_ARCS" / "arc_fantasy_templates.md"
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8")
    m = re.search(r"(## АРК 1.*?)(?=\n## АРК 2|\Z)", content, re.DOTALL)
    if not m:
        return ""
    block = re.sub(r"\n{3,}", "\n\n", m.group(1).strip())
    return "ШАБЛОН АРКИ (структура нарастания):\n" + block


def _load_arc_by_heading(engine_path: Path, heading: str) -> str:
    p = engine_path / "12_ARCS" / "arcs_by_genre.md"
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8")
    pattern = rf"(## {heading}[^\n]*\n.*?)(?=\n## [А-ЯЁ]|\Z)"
    m = re.search(pattern, content, re.DOTALL)
    if not m:
        return ""
    block = re.sub(r"\n{3,}", "\n\n", m.group(1).strip())
    return "ШАБЛОН АРКИ (структура нарастания):\n" + block


# _CHAR_FULL_KEY_MAP → импортируется из engine_config.CHAR_FULL_KEY_MAP

# _CHAR_FAMILY_FALLBACK → импортируется из engine_config.CHAR_FAMILY_FALLBACK

# _ANT_MAP → импортируется из engine_config.ANTAGONIST_GENRE_MAP


def load_character_profile(engine_path: Path, genre_key: str) -> str:
    """
    Загрузить жанровый профиль персонажа из 05_CHARACTER_ENGINE/profiles/GENRE/.
    Добавляет секцию антагониста если доступна.
    """
    if not genre_key:
        return ""

    genre_family = genre_key.split("_")[0]
    subgenre = genre_key.split("_", 1)[1] if "_" in genre_key else ""
    profiles_dir = engine_path / "05_CHARACTER_ENGINE" / "profiles" / "GENRE"

    fname = CHAR_FULL_KEY_MAP.get(genre_key) or CHAR_FAMILY_FALLBACK.get(genre_family)
    if not fname:
        return ""

    profile_path = profiles_dir / fname
    if not profile_path.exists():
        family_fname = CHAR_FAMILY_FALLBACK.get(genre_family, "")
        if family_fname:
            profile_path = profiles_dir / family_fname
        if not profile_path.exists():
            return ""

    try:
        profile_text = profile_path.read_text(encoding="utf-8").strip()
        ant_section = _load_antagonist_section(engine_path, genre_family, subgenre)
        return f"ПРОФИЛЬ ПЕРСОНАЖА ({genre_key}):\n{profile_text}{ant_section}"
    except Exception:
        return ""


def _load_antagonist_section(engine_path: Path, genre_family: str, subgenre: str) -> str:
    ant_path = engine_path / "05_CHARACTER_ENGINE" / "antagonists" / "antagonist_by_genre.md"
    if not ant_path.exists():
        return ""
    ant_text = ant_path.read_text(encoding="utf-8")
    ant_keyword = "НУАР" if subgenre == "noir" else ANTAGONIST_GENRE_MAP.get(genre_family, "")
    if not ant_keyword:
        return ""
    m = re.search(
        rf"###?\s*{ant_keyword}[^\n]*(.*?)(?=\n###?|\Z)",
        ant_text, re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return ""
    lines = [l for l in m.group(1).strip().splitlines() if l.strip()][:8]
    if not lines:
        return ""
    return "\n\nАНТАГОНИСТ ЖАНРА:\n" + "\n".join(lines)


def load_catalog_subgenre_hint(engine_path: Path, genre_key: str) -> str:
    """Загрузить специфику поджанра из catalog/{genre_key}.json."""
    if not genre_key:
        return ""
    catalog_path = engine_path / "04_GENRE_ENGINE" / "catalog" / f"{genre_key}.json"
    if not catalog_path.exists():
        return ""
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        lines = []
        if data.get("display_name"):
            lines.append(f"ПОДЖАНР: {data['display_name']}")
        if data.get("key_elements"):
            lines.append("КЛЮЧЕВЫЕ ЭЛЕМЕНТЫ: " + ", ".join(data["key_elements"]))
        if data.get("tone"):
            lines.append(f"ТОН: {data['tone']}")
        if data.get("mistakes"):
            lines.append("ТИПИЧНЫЕ ОШИБКИ ПОДЖАНРА (избегать): " + "; ".join(data["mistakes"]))
        if not lines:
            return ""
        return "СПЕЦИФИКА ПОДЖАНРА:\n" + "\n".join(lines)
    except Exception:
        return ""


_SUBGENRE_PROMPT_LABELS: dict[str, list[str]] = {
    "dark":             ["ТЁМНОЕ ФЭНТЕЗИ:", "ТЕМНОЕ ФЭНТЕЗИ:", "DARK FANTASY:"],
    "epic":             ["ЭПИЧЕСКОЕ:"],
    "urban":            ["ГОРОДСКОЕ:"],
    "romantic":         ["РОМАНТИЧЕСКОЕ:"],
    "sword_sorcery":    ["МЕЧ И МАГИЯ:", "SWORD AND SORCERY:"],
    "noir":             ["НУАР:", "NOIR:"],
    "classic":          ["КЛАССИЧЕСКИЙ:"],
    "procedural":       ["ПРОЦЕДУРНЫЙ:"],
    "psychological":    ["ПСИХОЛОГИЧЕСКИЙ:"],
    "cozy":             ["УЮТНЫЙ:", "COZY:"],
    "action":           ["БОЕВОЙ:"],
    "cosmic":           ["КОСМИЧЕСКИЙ:"],
    "gothic":           ["ГОТИЧЕСКИЙ:"],
    "survival":         ["ВЫЖИВАНИЯ:"],
    "spy":              ["ШПИОНСКИЙ:"],
    "cyberpunk":        ["КИБЕРПАНК:"],
    "hard":             ["ТВЁРДАЯ НФ:", "ТВЕРДАЯ НФ:", "HARD SF:"],
    "space_opera":      ["КОСМИЧЕСКАЯ ОПЕРА:"],
    "post_apocalyptic": ["ПОСТАПОК:", "ПОСТ-АПОК:"],
    "steampunk":        ["СТИМПАНК:"],
    "social":           ["СОЦИАЛЬНЫЙ:", "СОЦИАЛЬНАЯ НФ:"],
    "contemporary":     ["СОВРЕМЕННАЯ:", "CONTEMPORARY:"],
    "historical":       ["ИСТОРИЧЕСКАЯ:", "HISTORICAL:"],
    "paranormal":       ["ПАРАНОРМАЛЬНАЯ:"],
    "family_saga":      ["СЕМЕЙНАЯ САГА:"],
}


def load_genre_prompt(engine_path: Path, genre_key: str, mode: str) -> str:
    """
    Загрузить жанровый промпт из 11_PROMPTS/{family}_{MODE}.md.
    Извлекает конкретные правила поджанра.

    Если поджанровый блок найден но короткий (< 200 символов, типично для
    QUALITY/MASTER где используется однострочный компактный формат),
    дополняет его блоком из QUICK-файла (там правила развёрнуты на несколько строк).
    В любом случае добавляет load_catalog_subgenre_hint — JSON-данные каталога
    (key_elements, tone, mistakes) которые строго специфичны для поджанра.
    """
    if not genre_key:
        return ""
    family = genre_key.split("_")[0]
    subgenre = genre_key.split("_", 1)[1] if "_" in genre_key else ""
    path = engine_path / "11_PROMPTS" / f"{family}_{mode.upper()}.md"
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
        result = _extract_subgenre_block(text, genre_key, subgenre)
        if result:
            # Если блок тонкий (компактный 1-строчный формат QUALITY/MASTER),
            # добираем из QUICK-файла — там правила развёрнуты
            if len(result) < 200 and mode.upper() != "QUICK":
                quick_path = engine_path / "11_PROMPTS" / f"{family}_QUICK.md"
                if quick_path.exists():
                    try:
                        quick_text = quick_path.read_text(encoding="utf-8")
                        quick_block = _extract_subgenre_block(quick_text, genre_key, subgenre)
                        # Добавляем только строки которых нет в текущем результате
                        if quick_block:
                            existing_lines = set(result.splitlines())
                            extra = [
                                l for l in quick_block.splitlines()
                                if l.strip() and l not in existing_lines
                                and not l.startswith("ПРАВИЛА ЖАНРА")
                            ]
                            if extra:
                                result = result + "\n" + "\n".join(extra)
                    except Exception as e:
                        # Без QUICK-блока промпт беднее, но рабочий.
                        # Молчать нельзя: отказ чтения файла базы знаний
                        # иначе не проявится нигде.
                        from .logger import get_logger
                        get_logger(__name__).error(
                            "жанровый блок QUICK не подклеен", e,
                            reason=genre_key)
            # Всегда добавляем каталожную специфику поджанра
            catalog_addon = load_catalog_subgenre_hint(engine_path, genre_key)
            return (result + "\n" + catalog_addon) if catalog_addon else result
        return _extract_quality_rules_fallback(text, genre_key, family, engine_path)
    except Exception:
        return ""


def _extract_subgenre_block(text: str, genre_key: str, subgenre: str) -> str:
    """Извлечь блок правил для конкретного поджанра."""
    labels = _SUBGENRE_PROMPT_LABELS.get(subgenre, [])
    for label in labels:
        idx = text.find(label)
        if idx < 0:
            continue
        chunk = text[idx + len(label):]
        end = re.search(r"\n[А-ЯЁA-Z][А-ЯЁA-Z\s]{3,}:", chunk)
        if end:
            chunk = chunk[:end.start()]
        lines = []
        for line in chunk.splitlines():
            line = line.strip()
            if not line or line.startswith("[") or line.startswith("```"):
                continue
            lines.append(line)
            if len(lines) >= 8:
                break
        if lines:
            return f"ПРАВИЛА ЖАНРА ({genre_key}):\n" + "\n".join(lines)
    return ""


def _extract_quality_rules_fallback(
    text: str, genre_key: str, family: str, engine_path: Path
) -> str:
    """Fallback: блок ОБЯЗАТЕЛЬНО из секции ПРАВИЛА КАЧЕСТВА."""
    m = re.search(r"═══ ПРАВИЛА КАЧЕСТВА ═══\s*\n(.*?)(?=═══|\Z)", text, re.DOTALL)
    if m:
        m2 = re.search(r"ОБЯЗАТЕЛЬНО[^:]*:\s*\n(.*?)(?=═══|ЗАПРЕЩЕНО|\Z)", m.group(1), re.DOTALL)
        if m2:
            lines = []
            for line in m2.group(1).splitlines():
                line = line.strip().lstrip("- ")
                if line and not line.startswith("["):
                    lines.append(line)
                    if len(lines) >= 6:
                        break
            if lines:
                catalog_addon = load_catalog_subgenre_hint(engine_path, genre_key)
                base = f"ПРАВИЛА ЖАНРА ({family}):\n" + "\n".join(lines)
                return (base + "\n" + catalog_addon) if catalog_addon else base
    return load_catalog_subgenre_hint(engine_path, genre_key)
