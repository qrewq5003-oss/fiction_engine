"""
engine_loaders_genre.py — загрузчики жанровых блоков движка.

Ответственность: жанровый каталог, контракты, промпты, профили персонажей,
арки, специфика поджанра — всё что зависит от genre_key.
"""

import json
import re
from pathlib import Path
from .engine_config import (
    CONTRACT_MAP,
    CHAR_FULL_KEY_MAP, CHAR_FAMILY_FALLBACK, ANTAGONIST_GENRE_MAP,
)
from .logger import get_logger

# Загрузчик только пишет в лог, почему раздел пуст. Автору пропажу
# показывает сборка блока (unified_engine._note_missing_sections):
# там известно, какой раздел в этом режиме обязателен.
log = get_logger(__name__)


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
    except Exception as e:
        log.error("каталог жанра не прочитан", e, reason=genre_key)
        return ""


# _CONTRACT_MAP → импортируется из engine_config.CONTRACT_MAP

# ─── Якоря жанров в файлах базы ─────────────────────────────────────────────
#
# Раздел поджанра в контрактах (16_GENRE_CONTRACT) и блок правил в жанровых
# промптах (11_PROMPTS) помечены строкой «<!-- genre: ключ, ключ -->». Раньше
# они искались подстрокой русской метки по таблицам SUBGENRE_CONTRACT_LABELS и
# _SUBGENRE_PROMPT_LABELS: «ИСТОРИЧЕСКИЙ» не находил «ИСТОРИЧЕСКАЯ РОМАНТИКА»,
# и 15 поджанров получали чужой контракт (AUDIT_UNIFIED.md, U1). По ключу
# ошибиться нечем: раздел либо помечен этим ключом, либо его нет.
# Якорь — служебная строка, модели он не передаётся.

_ANCHOR = re.compile(r"^\s*<!--\s*genre:\s*(.*?)\s*-->\s*$")


def _anchor_keys(line: str) -> set[str]:
    m = _ANCHOR.match(line)
    return {k.strip() for k in m.group(1).split(",")} if m else set()


def load_genre_contract(engine_path: Path, genre_key: str) -> str:
    """Загрузить читательский контракт жанра."""
    genre_family = genre_key.split("_")[0]
    fname = CONTRACT_MAP.get(genre_family)
    if not fname:
        return ""
    p = engine_path / "16_GENRE_CONTRACT" / fname
    if not p.exists():
        return ""
    lines = p.read_text(encoding="utf-8").split("\n")
    # Раздел — от заголовка «## », под которым стоит якорь с этим ключом
    start = None
    header = None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            header = i
        elif genre_key in _anchor_keys(line) and header is not None:
            start = header
            break
    # Чужой контракт хуже пустого: без своего раздела — пусто и запись в лог
    if start is None:
        log.warning("раздел контракта не найден", f"{genre_key}: нет якоря в {fname}")
        return ""

    result = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("## ") or len(result) >= 30:
            break
        if not _ANCHOR.match(line):
            result.append(line)

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
    except Exception as e:
        log.error("профиль персонажа не прочитан", e, reason=genre_key)
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


# Семейство жанра → раздел 14_CHARACTER_DIALECTICS/dialectics_by_genre.md
DIALECTICS_GENRE_LABELS: dict[str, str] = {
    "detective": "ДЕТЕКТИВ",
    "thriller":  "ТРИЛЛЕР",
    "romance":   "РОМАНТИКА",
    "horror":    "ХОРРОР",
    "scifi":     "НФ",
    "fantasy":   "ФЭНТЕЗИ",
    "realism":   "РЕАЛИЗМ",
}


def load_dialectics_genre_hint(engine_path: Path, genre_key: str | None) -> str:
    """
    Жанровый раздел диалектики: какие параметры персонажа критичны и
    типичные конфликты. «Пример заполненного параметра» не берётся —
    это готовая реплика, модель переносила бы её в текст.
    """
    label = DIALECTICS_GENRE_LABELS.get((genre_key or "").split("_")[0])
    p = engine_path / "14_CHARACTER_DIALECTICS" / "dialectics_by_genre.md"
    if not label or not p.exists():
        return ""
    m = re.search(rf"^## {label}\s*\n(.*?)(?=^## |\Z)", p.read_text(encoding="utf-8"),
                  re.M | re.S)
    if not m:
        return ""
    body = re.split(r"^### Пример", m.group(1), flags=re.M)[0]
    body = re.sub(r"\n?---\s*$", "", body.strip()).strip()
    return f"ДИАЛЕКТИКА ЖАНРА ({label}):\n{body}" if body else ""


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
    except Exception as e:
        log.error("специфика поджанра не прочитана", e, reason=genre_key)
        return ""


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
    path = engine_path / "11_PROMPTS" / f"{family}_{mode.upper()}.md"
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        log.error("жанровые правила не прочитаны", e, reason=genre_key)
        return ""
    result = _extract_subgenre_block(text, genre_key)
    if not result:
        # Раньше тут шёл запасной разбор «ПРАВИЛА КАЧЕСТВА» семейства.
        # Для всех ключей блок поджанра есть (test_unified_contract),
        # так что запасной путь не выполнялся, а сработав для нового
        # ключа, молча отдал бы общие правила вместо своих.
        log.warning("блок правил поджанра не найден", f"{genre_key}: {path.name}")
        return ""
    # Если блок тонкий (компактный 1-строчный формат QUALITY/MASTER),
    # добираем из QUICK-файла — там правила развёрнуты
    if len(result) < 200 and mode.upper() != "QUICK":
        quick_path = engine_path / "11_PROMPTS" / f"{family}_QUICK.md"
        if quick_path.exists():
            try:
                quick_text = quick_path.read_text(encoding="utf-8")
            except Exception as e:
                # Без QUICK-блока промпт беднее, но рабочий.
                # Молчать нельзя: отказ чтения файла базы знаний
                # иначе не проявится нигде.
                log.error("жанровый блок QUICK не подклеен", e, reason=genre_key)
                quick_text = ""
            quick_block = _extract_subgenre_block(quick_text, genre_key)
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
    # Всегда добавляем каталожную специфику поджанра
    catalog_addon = load_catalog_subgenre_hint(engine_path, genre_key)
    return (result + "\n" + catalog_addon) if catalog_addon else result


def _extract_subgenre_block(text: str, genre_key: str) -> str:
    """
    Блок правил поджанра: строка-метка («ТЁМНОЕ ФЭНТЕЗИ: …») под якорем с
    ключом и следующие строки до метки другого блока, не больше 8.
    """
    lines_all = text.split("\n")
    at = next((i for i, l in enumerate(lines_all) if genre_key in _anchor_keys(l)), None)
    if at is None or at + 1 >= len(lines_all):
        return ""
    label_line = lines_all[at + 1]
    colon = label_line.find(":")
    chunk = label_line[colon + 1:] + "\n" + "\n".join(lines_all[at + 2:])
    end = re.search(r"\n[А-ЯЁA-Z][А-ЯЁA-Z\s]{3,}:", chunk)
    if end:
        chunk = chunk[:end.start()]
    lines = []
    for line in chunk.splitlines():
        line = line.strip()
        if not line or line.startswith(("[", "```", "<!--")):
            continue
        lines.append(line)
        if len(lines) >= 8:
            break
    return f"ПРАВИЛА ЖАНРА ({genre_key}):\n" + "\n".join(lines) if lines else ""
