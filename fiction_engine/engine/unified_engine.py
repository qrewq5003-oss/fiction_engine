"""
UNIFIED ENGINE ROUTER v3.0

Оркестрирует сборку контекста из UNIFIED_ENGINE_MASTER.
Единственное место принятия стратегических решений о модулях.

Конфигурация (жанры, приоритеты, модули) → engine_config.py
Загрузка файлов движка                    → engine_loaders.py
"""

import json
import re

from .engine_config import (
    GENRE_KEYWORDS,
    MODE_MODULES,
    GENRE_MODULES,
    MODULE_LINE_LIMITS,
)
from .engine_loaders import (
    engine_available,
    get_engine_path,
    get_token_budget,
    _trim_modules_to_budget,
    _load_module,
    _load_genre_catalog,
    _load_anticliche_replacements,
    _load_genre_contract,
    _load_dialectics_hint,
    _load_arc_hint,
    _load_character_profile,
    _load_symbolism_hint,
    _load_voice_check_hint,
    _load_genre_prompt,
    _load_writing_core_hint,
    _load_pattern_library,
)


# ─── Определение жанра ────────────────────────────────────────────────────────

def detect_genre(genre_text: str) -> str | None:
    """
    Определить жанровый ключ по тексту.
    Выбирает наиболее специфичное совпадение (длиннейший keyword).
    Нормализует ё→е для надёжного матчинга.
    """
    g = genre_text.lower().strip().replace("ё", "е")
    best_key = None
    best_len = 0
    for key, keywords in GENRE_KEYWORDS.items():
        for kw in keywords:
            kw_norm = kw.replace("ё", "е")
            if kw_norm in g and len(kw_norm) > best_len:
                best_key = key
                best_len = len(kw_norm)
    return best_key


# ─── Граф зависимостей ────────────────────────────────────────────────────────

def resolve_dependencies(modules: list[str]) -> list[str]:
    """Добавить зависимые модули в правильном порядке.
    
    Граф зависимостей читается из INDEX.json если там есть ключ
    module_dependencies, иначе используется хардкод из engine_config.py.
    """
    from .engine_loaders import get_module_dependencies
    dependencies = get_module_dependencies()

    resolved = list(modules)
    changed = True
    while changed:
        changed = False
        for m in list(resolved):
            for dep in dependencies.get(m, []):
                if dep not in resolved:
                    resolved.insert(0, dep)
                    changed = True
    seen = set()
    result = []
    for m in resolved:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


# ─── Динамический выбор модулей (master + LLM) ────────────────────────────────

def resolve_modules_dynamic(task_text: str, genre_key: str, api_call_fn) -> list[str]:
    """
    Динамический выбор модулей для master-режима через быстрый вызов модели.

    api_call_fn — функция вызова модели: (prompt: str) -> str.
    Ожидается дешёвая быстрая модель (haiku или аналог).
    Возвращает список модулей поверх базовых.
    """
    BASE_MODULES = [
        "07_voice_consistency",
        "19_hooks_closings",
        "10_subtext_engine",
    ]

    AVAILABLE_MODULES = {
        "01_tension_curve":             "нарастание напряжения, конфликт, противостояние, саспенс",
        "02_character_resonance":       "резонанс между персонажами, эмоциональная связь",
        "03_thematic_dna":              "тема произведения, идея, смысловой слой",
        "04_reader_simulation":         "читательское ожидание, предсказуемость, обман ожиданий, коммерция",
        "06_multibook_causality":       "связи между книгами серии, долгосрочные последствия",
        "09_deep_character_psychology": "глубокая психология персонажа, травма, мотивация, внутренний мир",
        "11_micromoments_library":      "маленькие детали, бытовые жесты, микромоменты, замедление",
        "12_pacing_engine":             "темп, ритм сцены, управление скоростью",
        "13_foreshadowing_engine":      "предзнаменования, символы, подготовка финала, намёки",
        "14_narrative_distance":        "дистанция нарратора, близость к персонажу",
        "15_dialogue_style":            "диалог, речевые паттерны, подтекст в репликах, разговор",
        "16_pov_filters":               "фокал, точка зрения, фильтрация через персонажа",
        "17_character_chemistry":       "химия между персонажами, динамика отношений, притяжение",
        "18_beats_rhythm":              "биты сцены, структура удара, пауза, динамика",
        "20_stakes_escalation":         "ставки, что теряется, цена выбора, драма",
        "22_sensory_immersion":         "сенсорная детализация, запахи, звуки, текстуры, атмосфера",
        "23_literary_craft":            "литературное мастерство, стиль, метафора, красота языка",
        "24_artistic_foundation":       "художественная база, emotion→language, поэтичность, образность, сенсорика",
        "25_style_transformations":     "трансформация стиля: нуар, минимализм, барокко, лирика, документ и др.",
    }

    ROUTING_HINTS = """
ПОДСКАЗКИ ДЛЯ ВЫБОРА (ключевые слова → модули):

Стиль и красота: "красиво, поэтично, образно, атмосфера, литературно" → 24_artistic_foundation, 23_literary_craft, 22_sensory_immersion
Трансформация стиля: "нуар, минимализм, барокко, лирика, документальный" → 25_style_transformations
Диалог: "диалог, реплики, разговор, подтекст в словах" → 15_dialogue_style, 10_subtext_engine, 11_micromoments_library
Напряжение: "напряжение, саспенс, тревога, конфликт, накал" → 01_tension_curve, 20_stakes_escalation, 13_foreshadowing_engine
Темп: "быстро, динамика, экшен" → 12_pacing_engine, 18_beats_rhythm; "медленно, растянуть, деталь" → 11_micromoments_library
Персонаж: "психология, внутренний мир, мотивация, травма" → 09_deep_character_psychology, 16_pov_filters
Химия: "отношения, химия, притяжение, динамика между" → 17_character_chemistry, 02_character_resonance
Сюжет/серия: "арка, серия, последствия, долгосрочно" → 06_multibook_causality, 03_thematic_dna
Эмоция: "эмоция, чувства, переживание" → 11_micromoments_library, 09_deep_character_psychology, 24_artistic_foundation
"""

    modules_desc = "\n".join(f'- "{k}": {v}' for k, v in AVAILABLE_MODULES.items())

    prompt = f"""Ты помогаешь писателю выбрать нужные инструменты для написания сцены.

Задача писателя:
{task_text}

Жанр: {genre_key or "не определён"}

{ROUTING_HINTS}

Доступные модули (выбери 3-6 наиболее нужных для ЭТОЙ конкретной задачи):
{modules_desc}

Ответь ТОЛЬКО валидным JSON — список строк с именами модулей.
Пример: ["09_deep_character_psychology", "17_character_chemistry", "20_stakes_escalation"]
Никакого текста до или после JSON."""

    try:
        raw = api_call_fn(prompt)
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if not match:
            return BASE_MODULES
        selected = json.loads(match.group())
        valid = [m for m in selected if m in AVAILABLE_MODULES]
        result = list(BASE_MODULES)
        for m in valid:
            if m not in result:
                result.append(m)
        return result
    except Exception:
        return list(MODE_MODULES["master"])


# ─── Выбор стратегии модулей ──────────────────────────────────────────────────

def _select_modules(
    mode: str,
    genre_key: str | None,
    pre_selected_modules: list | None,
    task_text: str,
    api_call_fn,
) -> list[str]:
    """
    Единственное место где выбирается стратегия модулей.

    Три стратегии в порядке приоритета:
    1. pre_selected_modules — явно переданные (из auto_router). Быстро, бесплатно.
    2. resolve_modules_dynamic — LLM выбирает. Точнее для нестандартных задач.
    3. MODE_MODULES[mode] + GENRE_MODULES[genre_key] — статический fallback.
    """
    if pre_selected_modules is not None:
        modules = list(pre_selected_modules)
    elif mode == "master" and task_text and api_call_fn is not None:
        modules = resolve_modules_dynamic(task_text, genre_key, api_call_fn)
    else:
        modules = list(MODE_MODULES[mode])
        if genre_key and genre_key in GENRE_MODULES:
            for m in GENRE_MODULES[genre_key]:
                if m not in modules:
                    modules.append(m)
    return resolve_dependencies(modules)


# ─── Сборка контекста ─────────────────────────────────────────────────────────

def build_engine_context(
    genre_text: str,
    mode: str = "quick",
    model_value: str = "",
    include_dialectics: bool = False,
    task_text: str = "",
    api_call_fn=None,
    pre_selected_modules: list | None = None,
) -> str:
    """
    Собирает контекст UNIFIED_ENGINE.
    Жанр + режим → правильные модули с зависимостями → бюджет → суть.

    Все стратегические решения о модулях делегированы в _select_modules().
    Этот метод — чистый orchestrator.
    """
    if not engine_available():
        return ""

    mode = mode if mode in MODE_MODULES else "quick"
    genre_key = detect_genre(genre_text)

    token_budget = get_token_budget(model_value)
    # 0.35 бюджета окна — на блок движка. Пересчёт токенов в символы идёт по
    # реальному отношению для смешанного русского текста, а не по английским
    # 4 символам на токен: иначе блок оказывается в полтора раза тяжелее,
    # чем считает бюджет.
    from .pipeline_config import MIXED_CHARS_PER_TOKEN
    char_budget = int(token_budget * MIXED_CHARS_PER_TOKEN * 0.35)

    fixed_sections = _build_fixed_sections(genre_key, mode, include_dialectics, task_text)
    module_sections = _build_module_sections(
        mode, genre_key, pre_selected_modules, task_text, api_call_fn
    )

    fixed_chars = sum(len(c) for _, c in fixed_sections)
    module_budget = max(char_budget - fixed_chars, char_budget // 2)
    trimmed = _trim_modules_to_budget(module_sections, module_budget)

    sections = fixed_sections + [("_module", c) for c in trimmed]
    if not sections:
        return ""

    genre_label = genre_key or "универсальный"
    header = f"=== UNIFIED ENGINE v3 / {mode.upper()} / {genre_label} ==="
    body = "\n\n---\n\n".join(c for _, c in sections)
    return header + "\n\n" + body + "\n\n=== / UNIFIED ENGINE ==="


def _build_fixed_sections(
    genre_key: str | None,
    mode: str,
    include_dialectics: bool,
    task_text: str = "",
) -> list[tuple[str, str]]:
    """
    Собирает фиксированные секции контекста (1-9).
    Возвращает [(name, content), ...].
    """
    sections = []

    if genre_key:
        _append_if(sections, "_catalog", _load_genre_catalog(genre_key))
        _append_if(sections, "_genre_rules", _load_genre_prompt(genre_key, mode))

    if genre_key and mode in ("quality", "master"):
        _append_if(sections, "_contract", _load_genre_contract(genre_key))

    _append_if(sections, "_anticliche", _load_anticliche_replacements())

    if include_dialectics and mode == "master":
        _append_if(sections, "_dialectics", _load_dialectics_hint())

    if genre_key and mode == "master":
        _append_if(sections, "_arc", _load_arc_hint(genre_key))

    if genre_key:
        char_profile = _load_character_profile(genre_key)
        if char_profile:
            if mode == "quick":
                char_profile = _trim_char_profile(char_profile, max_chars=800)
            sections.append(("_char_profile", char_profile))

    # 01_WRITING_CORE — выбираем 1-2 модуля по ключевым словам задачи
    if task_text:
        _append_if(sections, "_writing_core", _load_writing_core_hint(task_text, mode))

    # 06_PATTERN_LIBRARY — хуки, переходы, ситуации, паттерны сцен
    _append_if(sections, "_pattern_lib", _load_pattern_library(genre_key, mode, task_text))

    if mode in ("quality", "master"):
        _append_if(sections, "_symbolism", _load_symbolism_hint())
        _append_if(sections, "_voice_check", _load_voice_check_hint())

    return sections


def _build_module_sections(
    mode: str,
    genre_key: str | None,
    pre_selected_modules: list | None,
    task_text: str,
    api_call_fn,
) -> list[tuple[str, str]]:
    """
    Загружает и форматирует секции модулей движка.
    Возвращает [(module_name, formatted_content), ...].
    """
    line_limit = MODULE_LINE_LIMITS[mode]
    modules = _select_modules(
        mode=mode,
        genre_key=genre_key,
        pre_selected_modules=pre_selected_modules,
        task_text=task_text,
        api_call_fn=api_call_fn,
    )
    result = []
    for module in modules:
        content = _load_module(module, line_limit)
        if not content.strip():
            continue
        label = module.split("_", 1)[-1].replace("_", " ").upper() if "_" in module else module.upper()
        result.append((module, f"[{label}]\n{content}"))
    return result


def _append_if(sections: list, name: str, content: str) -> None:
    """Добавить секцию если content непустой."""
    if content:
        sections.append((name, content))


def _trim_char_profile(profile: str, max_chars: int) -> str:
    """Обрезать профиль персонажа до max_chars символов (по строкам)."""
    lines = profile.splitlines()
    trimmed, char_count = [], 0
    for line in lines:
        trimmed.append(line)
        char_count += len(line) + 1
        if char_count >= max_chars:
            break
    return "\n".join(trimmed)


# ─── Утилиты ──────────────────────────────────────────────────────────────────

def get_all_genre_options() -> list[dict]:
    if not engine_available():
        return []
    catalog_path = get_engine_path() / "04_GENRE_ENGINE" / "catalog"
    options = []
    for f in sorted(catalog_path.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            options.append({
                "key": f.stem,
                "label": data.get("display_name", f.stem),
                "description": data.get("description", ""),
            })
        except Exception:
            pass
    return options


def get_active_modules(genre_text: str, mode: str = "quick") -> list[str]:
    """Список активных модулей для данного жанра и режима (с зависимостями)."""
    genre_key = detect_genre(genre_text)
    modules = list(MODE_MODULES.get(mode, MODE_MODULES["quick"]))
    if genre_key and genre_key in GENRE_MODULES:
        for m in GENRE_MODULES[genre_key]:
            if m not in modules:
                modules.append(m)
    return resolve_dependencies(modules)
