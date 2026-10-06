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

CHAPTER_TONE_HEADER = "[ТОН ГЛАВЫ"

_PROFILES = "05_CHARACTER_ENGINE/profiles/GENRE"
_TONES = "17_TONE_LAYERS"

# Модификатор (тон или аудитория): название, файл в базе, модули, жанровые
# варианты модулей, которые он открывает, и можно ли взять его на одну главу.
#
# variants — метки «**ХОРРОР:** …» в модулях: у жути они ближе всего к делу,
# и глава с жутью в детективе получает хоррор-подсказки, как второй жанр.
# young_adult — аудитория всей книги: подростком на одну главу не станешь.
MODIFIERS: dict[str, dict] = {
    "comedy": {"label": "Комедия", "path": f"{_PROFILES}/comedic.md",
               "modules": ["15_dialogue_style", "11_micromoments_library"],
               "variants": frozenset(), "chapter": True},
    "young_adult": {"label": "Подростковая проза (YA)", "path": f"{_PROFILES}/young_adult.md",
                    "modules": ["09_deep_character_psychology", "16_pov_filters"],
                    "variants": frozenset(), "chapter": False},
    "dread":    {"label": "Жуть", "path": f"{_TONES}/dread.md",
                 "modules": ["22_sensory_immersion", "14_narrative_distance"],
                 "variants": frozenset({"ХОРРОР"}), "chapter": True},
    "action":   {"label": "Экшн", "path": f"{_TONES}/action.md",
                 "modules": ["18_beats_rhythm", "12_pacing_engine"],
                 "variants": frozenset({"ТРИЛЛЕР"}), "chapter": True, "rhythm": True},
    "suspense": {"label": "Саспенс", "path": f"{_TONES}/suspense.md",
                 "modules": ["01_tension_curve", "13_foreshadowing_engine"],
                 "variants": frozenset({"ТРИЛЛЕР"}), "chapter": True},
    "lyric":    {"label": "Лирика", "path": f"{_TONES}/lyric.md",
                 "modules": ["11_micromoments_library", "22_sensory_immersion"],
                 "variants": frozenset({"РЕАЛИЗМ"}), "chapter": True, "rhythm": True},
    "romance":  {"label": "Романтика", "path": f"{_TONES}/romance.md",
                 "modules": ["17_character_chemistry", "10_subtext_engine"],
                 "variants": frozenset({"РОМАНТИКА"}), "chapter": True},
    "noir":     {"label": "Нуар", "path": f"{_TONES}/noir.md",
                 "modules": ["21_voice_constructor", "10_subtext_engine"],
                 "variants": frozenset({"НУАР"}), "chapter": True},
    "satire":   {"label": "Сатира", "path": f"{_TONES}/satire.md",
                 "modules": ["03_thematic_dna", "15_dialogue_style"],
                 "variants": frozenset(), "chapter": True},
    "epic":     {"label": "Эпика", "path": f"{_TONES}/epic.md",
                 "modules": ["20_stakes_escalation", "14_narrative_distance"],
                 "variants": frozenset({"ФЭНТЕЗИ"}), "chapter": True, "rhythm": True},
}

# Разделы файла модификатора, которые идут в промпт. Архетипы, динамика
# и диалог с примером — нет: пример реплики модель переносит в текст.
_MODIFIER_SECTIONS = ("СУТЬ", "ОБЯЗАТЕЛЬНЫЕ ХАРАКТЕРИСТИКИ", "ТИПИЧНЫЕ ОШИБКИ",
                      "ПРИЁМЫ", "ОШИБКИ")
_MISTAKE_SECTIONS = ("ТИПИЧНЫЕ ОШИБКИ", "ОШИБКИ")

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


def _contract_subsection(key: str, starts: tuple[str, ...], limit: int) -> list[str]:
    """Строки подраздела «### …» контракта поджанра, чей заголовок начинается с starts."""
    from .engine_loaders_genre import load_genre_contract
    lines: list[str] = []
    inside = False
    for raw in load_genre_contract(_engine_path(), key).split("\n"):
        line = raw.strip()
        if line.startswith("### "):
            inside = line[4:].upper().startswith(starts)
            continue
        if line.startswith("## ") and lines:
            break
        if inside and line and line != "---":
            lines.append(line)
    return lines[:limit]


def _contract_promises(key: str) -> list[str]:
    """Строки «Обязательно» из раздела контракта поджанра."""
    return _contract_subsection(key, ("ОБЯЗАТЕЛЬНО",), 4)


def _contract_violations(key: str) -> list[str]:
    """Строки «Нарушение контракта» (или «Запрещено») раздела поджанра."""
    return _contract_subsection(key, ("НАРУШЕНИЕ", "ЗАПРЕЩЕНО"), 6)


def _modifier_body(key: str) -> list[str]:
    p = _engine_path() / MODIFIERS[key]["path"]
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[str] = []
    # Суть у тонов — строкой «**Суть:** …» под заголовком файла
    core = re.search(r"^\*\*Суть:\*\*\s*(.+)$", text, re.M)
    if core:
        out.append(f"- {core.group(1).strip()}")
    for title, body in re.findall(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        if not any(title.upper().startswith(s) for s in _MODIFIER_SECTIONS):
            continue
        for raw in body.split("\n"):
            line = raw.strip().replace("**", "")
            if not line or line == "---" or line.startswith("#"):
                continue
            if title.upper().startswith(_MISTAKE_SECTIONS):
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


# ─── Тон главы ───────────────────────────────────────────────────────────────
#
# Тот же модификатор, но на одну главу и сверх второго слоя проекта:
# «детектив + романтика», а седьмая глава ещё и с жутью. Хранится за
# номером главы (chapter_tones), выбирается на страницах генерации.

def is_chapter_tone(key: str | None) -> bool:
    return bool(key) and key in MODIFIERS and MODIFIERS[key or ""]["chapter"]


def chapter_tone_options() -> list[dict]:
    return [{"key": k, "label": v["label"]} for k, v in MODIFIERS.items() if v["chapter"]]


def load_chapter_tone_section(key: str | None, project_secondary: str | None = None) -> str:
    """Раздел «Тон главы». Пусто — тона нет или он уже стоит на весь проект."""
    if not is_chapter_tone(key) or key == project_secondary:
        return ""
    body = _modifier_body(key or "")
    if not body:
        return ""
    return (f"{CHAPTER_TONE_HEADER}: {MODIFIERS[key or '']['label']}]\n"
            f"Только эта глава звучит так — поверх жанра и второго слоя книги. "
            f"Сюжет, персонажи и голос серии остаются прежними.\n" + "\n".join(body))


def layer_variant_labels(*keys: str | None) -> frozenset:
    """Метки жанровых вариантов модулей, которые открывают модификаторы."""
    out: frozenset = frozenset()
    for k in keys:
        if k in MODIFIERS:
            out = out | MODIFIERS[k or ""]["variants"]
    return out


# ─── Слои для критика и судьи ────────────────────────────────────────────────
#
# Генератор видит второй слой и тон главы, а критик и судья — только
# основной жанр. Лирическая глава в триллере для них «провисает», глава с
# жутью в детективе «уходит от жанра» — и оценка снижается за то, что автор
# выбрал нарочно. Эта справка говорит им, что выбрано, и что проверять:
# удался ли слой.

REVIEW_LAYERS_HEADER = "СЛОИ ГЛАВЫ"


def _core(key: str) -> str:
    body = _modifier_body(key)
    return body[0][2:].rstrip(".") if body else ""


def review_layers_note(project: dict | None, chapter_num: int | None = None) -> str:
    """Справка о втором слое книги и тоне главы. Пусто — слоёв нет."""
    if not project:
        return ""
    secondary = project_secondary_key(project)
    tone = None
    if chapter_num and project.get("id"):
        from .db import get_chapter_tone
        tone = get_chapter_tone(project["id"], chapter_num)
        if not is_chapter_tone(tone) or tone == secondary:
            tone = None
    lines = []
    if secondary in MODIFIERS:
        lines.append(f"- Тон всей книги: {secondary_label(secondary)} — {_core(secondary or '')}. "
                     f"Оцени, удался ли он.")
    elif secondary:
        lines.append(f"- Второй жанр книги: {secondary_label(secondary)}. Его линия — законная "
                     f"часть главы, его обещания читателю тоже оцениваются.")
    if tone:
        lines.append(f"- Тон этой главы: {secondary_label(tone)} — {_core(tone)}. Глава нарочно "
                     f"звучит иначе, чем обычно звучит жанр. Отход от привычного темпа и тона "
                     f"жанра, который работает на этот тон, не снижает оценку; снижает — если "
                     f"тон не получился.")
    if not lines:
        return ""
    return (f"{REVIEW_LAYERS_HEADER} (выбраны автором намеренно — оценивай с их учётом):\n"
            + "\n".join(lines))


# ─── Контракт второго жанра для судьи ────────────────────────────────────────
#
# Судья проверял контракт только основного жанра: «детектив + романтика»
# принимался с проваленной любовной линией. Обещания второго жанра идут
# ему отдельно и мягче: второй линии может не быть в конкретной главе.

SECONDARY_CONTRACT_HEADER = "НАРУШЕНИЯ ВТОРОГО ЖАНРА"


def secondary_contract_for_judge(project: dict | None) -> str:
    """
    Нарушения контракта второго жанра — что судье искать в главе. Пусто —
    второго жанра нет или вторым слоем стоит модификатор (у тона нет контракта).

    Раньше судья получал пункты «Обязательно», и из четырёх три были
    обещаниями всей книги (HEA, чёрный момент, «оба меняются»). Замер 06.10:
    проваленную линию («она поняла, что влюблена», химии нет) судья с таким
    контрактом оценивал выше, чем без него, — признания читал как шаг к HEA;
    разрыв с живой линией пропадал (−1.94 ± 0.48). Строка «Химии нет — они
    просто говорят что влюблены» была в разделе нарушений, которого судья
    не видел.
    """
    key = project_secondary_key(project)
    if not key or key in MODIFIERS:
        return ""
    from .unified_engine import project_genre_key
    if key == project_genre_key(project):
        return ""
    violations = _contract_violations(key) or _contract_promises(key)
    if not violations:
        return ""
    return (f"{SECONDARY_CONTRACT_HEADER} ({secondary_label(key)}) — вторая линия книги:\n"
            + "\n".join(f"- {p}" for p in violations)
            + "\n\nЕсли линия второго жанра в главе есть — проверь её на эти "
              "нарушения; найденное — замечание в вердикте и снижение оценки. Если "
              "её в этой главе нет — это не нарушение. Финал и развязку книги в "
              "отдельной главе не требуй. Контракт основного жанра важнее.")


# ─── Ритм тона вместо общей нормы ────────────────────────────────────────────
#
# В промпт каждой главы идёт общая норма ритма (около 30 % коротких фраз,
# 20 % длинных — pipeline_config.RHYTHM_TARGET) с пометкой «по этому тебя
# оценивают». У лирики, эпики и экшна свой ритм, и две нормы спорили:
# замер 28.09 — лирика дала среднюю фразу 13.2 слова при ориентире 15–20,
# эпика 11.9. Для главы с таким тоном общая норма заменяется отсылкой к
# тону (rhythm: True в MODIFIERS).

def tone_rhythm_note(tone: str | None) -> str:
    """Замена общей нормы ритма для главы с тоном, у которого свой ритм."""
    if not is_chapter_tone(tone) or not MODIFIERS[tone or ""].get("rhythm"):
        return ""
    return (f"РИТМ ПРЕДЛОЖЕНИЙ — в этой главе его задаёт тон «{MODIFIERS[tone or '']['label']}»: "
            f"держи длину фраз и долю диалога, названные в разделе «ТОН ГЛАВЫ». "
            f"Общая норма ритма на эту главу не действует.")
