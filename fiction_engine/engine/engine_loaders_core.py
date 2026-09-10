"""
engine_loaders_core.py — загрузчики универсальных блоков движка.

Ответственность: модули (03_ADVANCED_ENGINES), антиклише, диалектика,
символика, чеклист голоса — блоки не зависящие от жанра.
"""

from pathlib import Path
from .engine_extractors import _extract_module_essence


def _find_module_file(engine_path: Path, module_name: str) -> Path | None:
    engines_path = engine_path / "03_ADVANCED_ENGINES"
    if not engines_path.exists():
        return None
    exact = engines_path / f"{module_name}.md"
    if exact.exists():
        return exact
    prefix = module_name.split("_")[0]
    if prefix.isdigit():
        for f in engines_path.glob(f"{prefix}_*.md"):
            return f
    return None


def load_module(engine_path: Path, module_name: str, max_lines: int = 40) -> str:
    f = _find_module_file(engine_path, module_name)
    if not f:
        return ""
    return _extract_module_essence(f.read_text(encoding="utf-8"), max_lines)


def load_anticliche_replacements(engine_path: Path) -> str:
    """Загрузить замены клише — самый ценный файл движка."""
    p = engine_path / "00_CORE" / "anticliche_replacements.md"
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8")
    lines = content.split("\n")
    result: list[str] = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and line.strip():
            result.append(line)
        if len(result) >= 50:
            break
    return "КЛИШЕ → ЗАМЕНЫ (используй замены, не запреты):\n" + "\n".join(result)


def load_dialectics_hint(engine_path: Path) -> str:
    """Загрузить краткую суть диалектики персонажей."""
    p = engine_path / "14_CHARACTER_DIALECTICS" / "dialectics_core.md"
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8")
    lines = content.split("\n")
    result = []
    in_template = False
    for line in lines:
        if "ШАБЛОН ДИАЛЕКТИКИ" in line or "## ЧТО ВХОДИТ" in line:
            in_template = True
        if in_template:
            result.append(line)
        if len(result) >= 35:
            break
    return "ДИАЛЕКТИКА ПЕРСОНАЖЕЙ (как они думают и решают):\n" + "\n".join(result)


def load_symbolism_hint(engine_path: Path) -> str:
    """Загрузить механику символов из 15_SYMBOLISM."""
    p = engine_path / "15_SYMBOLISM" / "symbolism_core.md"
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8")
    lines = content.split("\n")
    result: list[str] = []
    in_section = False
    for line in lines:
        if "ЧТО ТАКОЕ РАБОЧИЙ СИМВОЛ" in line or "ЧТО РАБОТАЕТ КАК СИМВОЛ" in line:
            in_section = True
        if in_section:
            if "РЕЕСТР СИМВОЛОВ" in line and result:
                break
            result.append(line)
        if len(result) >= 20:
            break
    if not result:
        return ""
    return "СИМВОЛИКА (повторяющиеся образы с нарастающим смыслом):\n" + "\n".join(result)


def load_voice_check_hint(engine_path: Path) -> str:
    """Загрузить чеклист голоса из 13_VOICE_LIBRARY/voice_check.md."""
    p = engine_path / "13_VOICE_LIBRARY" / "voice_check.md"
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8")
    lines = content.split("\n")
    result = []
    in_section = False
    for line in lines:
        if "САМОПРОВЕРКА" in line:
            in_section = True
        if in_section:
            if line.startswith("## ") and "САМОПРОВЕРКА" not in line:
                break
            result.append(line)
        if len(result) >= 15:
            break
    if not result:
        return ""
    return "ПРОВЕРКА ГОЛОСА:\n" + "\n".join(result)


# ─── 01_WRITING_CORE loader ──────────────────────────────────────────────────

# Карта: ключевые слова в задаче → файл writing core
_WRITING_CORE_MAP = {
    "01_dialogues":      ["диалог", "разговор", "допрос", "беседа", "разговаривает", "говорит",
                          "dialogue", "dialog", "речь", "реплик"],
    "03_action":         ["бой", "схватка", "погоня", "атака", "экшен", "действие", "драка",
                          "сражение", "бежит", "стреляет", "action", "fight", "битва"],
    "04_emotions":       ["эмоц", "чувств", "внутренний", "переживан", "emotion", "feel",
                          "состояни", "горе", "радость", "тревога", "страх", "любовь"],
    "02_descriptions":   ["описан", "атмосфер", "место", "пейзаж", "интерьер", "окружен",
                          "description", "место действия", "локация"],
    "05_pov":            ["pov", "точка зрения", "нарратор", "от лица", "голос", "повествован"],
    "06_scene_structure":["структур", "сцен", "глава", "chapter", "scene", "ритм", "темп"],
}


def load_writing_core_hint(engine_path: Path, task_text: str, mode: str) -> str:
    """
    Выбрать 1-2 релевантных файла из 01_WRITING_CORE по ключевым словам в задаче.
    quick: только 1 файл, 20 строк. quality+master: до 2 файлов, 30 строк каждый.
    """
    if not task_text:
        return ""
    wc_path = engine_path / "01_WRITING_CORE"
    if not wc_path.exists():
        return ""

    task_lower = task_text.lower()
    max_files   = 1 if mode == "quick" else 2
    max_lines   = 20 if mode == "quick" else 30

    matched: list[tuple[int, str]] = []  # (score, filename)
    for fname, keywords in _WRITING_CORE_MAP.items():
        score = sum(1 for kw in keywords if kw in task_lower)
        if score > 0:
            matched.append((score, fname))

    matched.sort(reverse=True)
    selected = [fname for _, fname in matched[:max_files]]

    if not selected:
        return ""

    parts = []
    for fname in selected:
        fpath = wc_path / f"{fname}.md"
        if not fpath.exists():
            continue
        content = fpath.read_text(encoding="utf-8")
        lines   = content.split("\n")
        result  = []
        for line in lines:
            stripped = line.strip()
            # Пропускаем метаданные-шапку и markdown-заголовки уровня 1
            if stripped.startswith("**Модуль:**") or stripped.startswith("**Размер:**") \
               or stripped.startswith("**Зависимости:**"):
                continue
            if stripped.startswith("```"):
                continue
            if stripped:
                result.append(line)
            if len(result) >= max_lines:
                break
        if result:
            label = fname.replace("0", "").replace("_", " ").strip().upper()
            parts.append(f"[ТЕХНИКА: {label}]\n" + "\n".join(result))

    return "\n\n".join(parts) if parts else ""


# ─── 10_VALIDATION loader ─────────────────────────────────────────────────────

_VALIDATION_GENRE_MAP = {
    "detective": "checklist_detective.md",
    "fantasy":   "checklist_fantasy.md",
    "horror":    "checklist_horror.md",
    "romance":   "checklist_romance.md",
    "thriller":  "checklist_thriller.md",
    "scifi":     "checklist_scifi.md",
    "realism":   "checklist_realism.md",
}


def load_validation_checklist(engine_path: Path, genre_key: str | None,
                               max_lines: int = 30) -> str:
    """
    Загружает чеклист для судьи из 10_VALIDATION/.
    Всегда universal + жанровый (если есть).
    max_lines на каждый файл.
    """
    val_path = engine_path / "10_VALIDATION"
    if not val_path.exists():
        return ""

    result_parts = []

    # Universal — всегда
    universal = val_path / "checklist_universal.md"
    if universal.exists():
        lines = universal.read_text(encoding="utf-8").split("\n")
        useful = [l for l in lines if l.strip() and not l.startswith("#")][:max_lines]
        if useful:
            result_parts.append("КРИТЕРИИ ОЦЕНКИ (универсальные):\n" + "\n".join(useful))

    # Жанровый — если есть
    if genre_key:
        family = genre_key.split("_")[0]
        genre_file = _VALIDATION_GENRE_MAP.get(family)
        if genre_file:
            gpath = val_path / genre_file
            if gpath.exists():
                lines = gpath.read_text(encoding="utf-8").split("\n")
                useful = [l for l in lines if l.strip() and not l.startswith("#")][:max_lines]
                if useful:
                    result_parts.append(f"КРИТЕРИИ ЖАНРА ({family}):\n" + "\n".join(useful))

    return "\n\n".join(result_parts) if result_parts else ""


# ─── 06_PATTERN_LIBRARY loader ────────────────────────────────────────────────

# Маппинг жанрового ключа → situations-файл
_PATTERN_GENRE_MAP = {
    "detective": "detective_situations.md",
    "fantasy":   "fantasy_situations.md",
    "horror":    "horror_situations.md",
    "romance":   "romance_situations.md",
    "scifi":     "scifi_situations.md",
    "thriller":  "thriller_situations.md",
    "realism":   "realism_situations.md",
}

# Маппинг ключевых слов задачи → файл сцены
_PATTERN_SCENE_MAP = {
    "dynamic_scene":    ["бой", "погоня", "бежит", "экшн", "схватка", "action", "fight", "атака"],
    "emotional_scene":  ["горе", "чувств", "слёзы", "прощание", "смерть", "любовь", "эмоц", "emotional"],
    "atmospheric_scene": ["атмосфер", "место", "описан", "пейзаж", "интерьер", "мрачн", "тихо"],
}


def _read_md_useful(path: Path, max_lines: int) -> list[str]:
    """Читает .md файл, пропуская шапку и code-блоки, возвращает значимые строки."""
    lines = path.read_text(encoding="utf-8").split("\n")
    result = []
    in_code = False
    skip_header = True  # пропускаем первый ## заголовок-шапку
    for line in lines:
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            result.append(line)
            continue
        if skip_header and s.startswith("**") and ("Назначение" in s or "Когда" in s):
            continue
        if skip_header and not s:
            continue
        if skip_header and s.startswith("---"):
            skip_header = False
            continue
        if s:
            result.append(line)
        if len(result) >= max_lines:
            break
    return result


def load_pattern_library(
    engine_path: Path,
    genre_key: str | None,
    mode: str,
    task_text: str = "",
) -> str:
    """
    Загружает из 06_PATTERN_LIBRARY релевантные паттерны:
    - hooks_by_genre.md (жанровый блок) — всегда
    - transitions/scene_transitions.md  — quality/master
    - genre_situations/{genre}.md или universal — quality/master
    - scenes/{тип}.md по ключевым словам задачи — если совпадение

    quick:          только хуки (жанровый раздел)
    quality/master: хуки + переходы + ситуации
    + scene-паттерн если task_text совпадает с ключевыми словами
    """
    pl_path = engine_path / "06_PATTERN_LIBRARY"
    if not pl_path.exists():
        return ""

    max_hook_lines = 20 if mode == "quick" else 30
    parts: list[str] = []

    # 1. Хуки по жанрам — всегда
    hooks_path = pl_path / "hooks_by_genre.md"
    if hooks_path.exists() and genre_key:
        family = genre_key.split("_")[0].upper()
        content = hooks_path.read_text(encoding="utf-8")
        # Вырезаем только раздел нужного жанра
        import re
        pattern = rf"## {family}.*?(?=\n## |\Z)"
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            block = match.group().strip()
            lines = [l for l in block.split("\n") if l.strip()][:max_hook_lines]
            parts.append("ХУКИ И КОНЦОВКИ ДЛЯ ЖАНРА:\n" + "\n".join(lines))

    # 2. Переходы между сценами (quality/master)
    if mode in ("quality", "master"):
        trans_path = pl_path / "transitions" / "scene_transitions.md"
        if trans_path.exists():
            lines = _read_md_useful(trans_path, max_lines=25)
            if lines:
                parts.append("ПЕРЕХОДЫ МЕЖДУ СЦЕНАМИ:\n" + "\n".join(lines))

    # 3. Ситуации (quality/master)
    if mode in ("quality", "master"):
        sit_dir = pl_path / "genre_situations"
        sit_file = None
        if genre_key:
            family = genre_key.split("_")[0]
            gf = _PATTERN_GENRE_MAP.get(family)
            if gf and (sit_dir / gf).exists():
                sit_file = sit_dir / gf
        if sit_file is None and (sit_dir / "universal_situations.md").exists():
            sit_file = sit_dir / "universal_situations.md"
        if sit_file:
            lines = _read_md_useful(sit_file, max_lines=35)
            if lines:
                label = sit_file.stem.replace("_", " ").upper()
                parts.append(f"ПАТТЕРНЫ СИТУАЦИЙ ({label}):\n" + "\n".join(lines))

    # 4. Паттерн сцены по ключевым словам задачи
    if task_text:
        task_lower = task_text.lower()
        scenes_path = pl_path / "scenes"
        best_file = None
        best_score = 0
        for fname, keywords in _PATTERN_SCENE_MAP.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > best_score:
                best_score = score
                best_file = fname
        if best_file and best_score >= 1:
            fp = scenes_path / f"{best_file}.md"
            if fp.exists():
                lines = _read_md_useful(fp, max_lines=25)
                if lines:
                    label = best_file.replace("_", " ").upper()
                    parts.append(f"ПАТТЕРН СЦЕНЫ ({label}):\n" + "\n".join(lines))

    return "\n\n".join(parts) if parts else ""
