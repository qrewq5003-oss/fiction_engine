"""
AUTO_ROUTER — быстрая маршрутизация модулей по ключевым словам задачи.

Логика:
  1. Первый проход: матчинг по словарю без вызова LLM
  2. Если уверенность высокая (3+ совпадений) — возвращаем результат сразу
  3. Если неоднозначно или задача сложная — передаём в LLM-резолвер

Преимущества:
  - Быстро (< 1мс для типичных задач)
  - Бесплатно (без API-вызова)
  - Предсказуемо (таблица видна и редактируема)
  - LLM подключается только когда нужен

Всегда добавляются BASE_MODULES поверх выбранных.
"""

from __future__ import annotations

# ─── Базовые модули (всегда в master) ────────────────────────────────────────

BASE_MODULES = [
    "07_voice_consistency",
    "19_hooks_closings",
    "10_subtext_engine",
]

# ─── Таблица маршрутизации ────────────────────────────────────────────────────
# Формат: "ключевое_слово": ["модуль1", "модуль2", ...]
# Слова нормализованы к нижнему регистру без знаков препинания.

KEYWORD_ROUTES: dict[str, list[str]] = {

    # Стиль и красота
    "красив":           ["24_artistic_foundation", "23_literary_craft"],
    "красиво":          ["24_artistic_foundation", "23_literary_craft"],
    "поэтич":           ["24_artistic_foundation", "23_literary_craft"],
    "поэтично":         ["24_artistic_foundation", "23_literary_craft"],
    "литературн":       ["23_literary_craft", "24_artistic_foundation"],
    "образн":           ["24_artistic_foundation", "22_sensory_immersion"],
    "образно":          ["24_artistic_foundation", "22_sensory_immersion"],
    "метафор":          ["24_artistic_foundation", "23_literary_craft"],
    "стил":             ["25_style_transformations", "23_literary_craft"],
    "стиль":            ["25_style_transformations", "23_literary_craft"],

    # Трансформация стиля
    "нуар":             ["25_style_transformations", "15_dialogue_style"],
    "минимализм":       ["25_style_transformations", "12_pacing_engine"],
    "минималистич":     ["25_style_transformations", "12_pacing_engine"],
    "барокко":          ["25_style_transformations", "23_literary_craft"],
    "барочн":           ["25_style_transformations", "23_literary_craft"],
    "лирик":            ["25_style_transformations", "24_artistic_foundation"],
    "лирично":          ["25_style_transformations", "24_artistic_foundation"],
    "документальн":     ["25_style_transformations"],
    "документ":         ["25_style_transformations"],
    "готик":            ["25_style_transformations", "22_sensory_immersion"],
    "экспрессион":      ["25_style_transformations", "24_artistic_foundation"],
    "сюрреализм":       ["25_style_transformations"],
    "магическ реализм": ["25_style_transformations", "24_artistic_foundation"],

    # Атмосфера и сенсорика
    "атмосфер":         ["22_sensory_immersion", "24_artistic_foundation"],
    "атмосфера":        ["22_sensory_immersion", "24_artistic_foundation"],
    "запах":            ["22_sensory_immersion"],
    "запахи":           ["22_sensory_immersion"],
    "звук":             ["22_sensory_immersion"],
    "текстур":          ["22_sensory_immersion"],
    "сенсорик":         ["22_sensory_immersion"],
    "описани":          ["22_sensory_immersion", "24_artistic_foundation"],
    "описание":         ["22_sensory_immersion", "24_artistic_foundation"],

    # Диалог
    "диалог":           ["15_dialogue_style", "10_subtext_engine"],
    "диалоги":          ["15_dialogue_style", "10_subtext_engine"],
    "реплик":           ["15_dialogue_style", "10_subtext_engine"],
    "разговор":         ["15_dialogue_style", "11_micromoments_library"],
    "речь":             ["15_dialogue_style"],
    "подтекст":         ["10_subtext_engine", "15_dialogue_style"],
    "невысказанн":      ["10_subtext_engine"],
    "скрыт":            ["10_subtext_engine", "13_foreshadowing_engine"],

    # Напряжение и конфликт
    "напряжени":        ["01_tension_curve", "20_stakes_escalation"],
    "напряжение":       ["01_tension_curve", "20_stakes_escalation"],
    "саспенс":          ["01_tension_curve", "13_foreshadowing_engine"],
    "тревог":           ["01_tension_curve", "22_sensory_immersion"],
    "конфликт":         ["01_tension_curve", "20_stakes_escalation"],
    "накал":            ["01_tension_curve", "18_beats_rhythm"],
    "противостоян":     ["01_tension_curve", "17_character_chemistry"],
    "ставк":            ["20_stakes_escalation"],
    "ставки":           ["20_stakes_escalation"],
    "драм":             ["01_tension_curve", "20_stakes_escalation"],
    "драма":            ["01_tension_curve", "20_stakes_escalation"],
    "угроз":            ["01_tension_curve", "20_stakes_escalation"],
    "опасност":         ["01_tension_curve", "22_sensory_immersion"],

    # Темп и ритм
    "темп":             ["12_pacing_engine", "18_beats_rhythm"],
    "ритм":             ["18_beats_rhythm", "12_pacing_engine"],
    "динамик":          ["12_pacing_engine", "18_beats_rhythm"],
    "динамика":         ["12_pacing_engine", "18_beats_rhythm"],
    "быстро":           ["12_pacing_engine", "18_beats_rhythm"],
    "быстрее":          ["12_pacing_engine", "18_beats_rhythm"],
    "экшен":            ["12_pacing_engine", "18_beats_rhythm"],
    "экшн":             ["12_pacing_engine", "18_beats_rhythm"],
    "медленно":         ["11_micromoments_library", "22_sensory_immersion"],
    "медленн":          ["11_micromoments_library", "22_sensory_immersion"],
    "замедл":           ["11_micromoments_library"],
    "растянуть":        ["11_micromoments_library", "22_sensory_immersion"],
    "паузу":            ["11_micromoments_library", "18_beats_rhythm"],

    # Микромоменты и детали
    "микромомент":      ["11_micromoments_library"],
    "детал":            ["11_micromoments_library", "22_sensory_immersion"],
    "деталь":           ["11_micromoments_library", "22_sensory_immersion"],
    "детали":           ["11_micromoments_library", "22_sensory_immersion"],
    "жест":             ["11_micromoments_library"],
    "жесты":            ["11_micromoments_library"],
    "движени":          ["11_micromoments_library", "18_beats_rhythm"],
    "бытов":            ["11_micromoments_library"],
    "обыденн":          ["11_micromoments_library"],

    # Персонаж и психология
    "психологи":        ["09_deep_character_psychology", "16_pov_filters"],
    "психологию":       ["09_deep_character_psychology", "16_pov_filters"],
    "внутренн":         ["09_deep_character_psychology", "16_pov_filters"],
    "мотивац":          ["09_deep_character_psychology"],
    "мотивация":        ["09_deep_character_psychology"],
    "травм":            ["09_deep_character_psychology"],
    "травма":           ["09_deep_character_psychology"],
    "страх":            ["09_deep_character_psychology", "22_sensory_immersion"],
    "желани":           ["09_deep_character_psychology", "17_character_chemistry"],
    "характер":         ["09_deep_character_psychology", "02_character_resonance"],

    # Химия и отношения
    "химия":            ["17_character_chemistry", "02_character_resonance"],
    "притяжени":        ["17_character_chemistry"],
    "притяжение":       ["17_character_chemistry"],
    "отношени":         ["17_character_chemistry", "02_character_resonance"],
    "отношения":        ["17_character_chemistry", "02_character_resonance"],
    "напряжени между":  ["17_character_chemistry", "01_tension_curve"],
    "любов":            ["17_character_chemistry", "11_micromoments_library"],
    "любовь":           ["17_character_chemistry", "11_micromoments_library"],
    "ненавист":         ["17_character_chemistry", "01_tension_curve"],
    "резонанс":         ["02_character_resonance"],

    # POV и нарратор
    "pov":              ["16_pov_filters", "14_narrative_distance"],
    "точка зрени":      ["16_pov_filters", "14_narrative_distance"],
    "фокал":            ["16_pov_filters"],
    "нарратор":         ["14_narrative_distance"],
    "повествовани":     ["14_narrative_distance", "16_pov_filters"],
    "дистанц":          ["14_narrative_distance"],

    # Эмоции
    "эмоци":            ["11_micromoments_library", "09_deep_character_psychology", "24_artistic_foundation"],
    "эмоция":           ["11_micromoments_library", "09_deep_character_psychology", "24_artistic_foundation"],
    "чувств":           ["24_artistic_foundation", "22_sensory_immersion"],
    "чувство":          ["24_artistic_foundation", "22_sensory_immersion"],
    "переживани":       ["09_deep_character_psychology", "11_micromoments_library"],
    "боль":             ["09_deep_character_psychology", "22_sensory_immersion"],
    "горе":             ["09_deep_character_psychology", "11_micromoments_library"],
    "радост":           ["11_micromoments_library", "24_artistic_foundation"],
    "радость":          ["11_micromoments_library", "24_artistic_foundation"],

    # Предзнаменования и структура
    "предзнаменовани":  ["13_foreshadowing_engine"],
    "намёк":            ["13_foreshadowing_engine", "10_subtext_engine"],
    "намек":            ["13_foreshadowing_engine", "10_subtext_engine"],
    "символ":           ["13_foreshadowing_engine", "03_thematic_dna"],
    "символика":        ["13_foreshadowing_engine"],
    "финал":            ["13_foreshadowing_engine", "19_hooks_closings"],
    "концовк":          ["19_hooks_closings"],
    "хук":              ["19_hooks_closings"],
    "зацеп":            ["19_hooks_closings"],
    "читател":          ["04_reader_simulation"],

    # Тема и смысл
    "тем":              ["03_thematic_dna", "10_subtext_engine"],
    "тема":             ["03_thematic_dna"],
    "смысл":            ["03_thematic_dna", "10_subtext_engine"],
    "идея":             ["03_thematic_dna"],
    "подтекст темы":    ["03_thematic_dna", "10_subtext_engine"],

    # Серия и долгосрочность
    "сери":             ["06_multibook_causality"],
    "серия":            ["06_multibook_causality"],
    "арк":              ["06_multibook_causality", "03_thematic_dna"],
    "арка":             ["06_multibook_causality"],
    "долгосрочн":       ["06_multibook_causality"],
    "последствия":      ["06_multibook_causality"],
    "следующая книга":  ["06_multibook_causality"],

    # Коммерция и читаемость
    "коммерц":          ["04_reader_simulation", "05_commercial_heatmap"],
    "продаваем":        ["04_reader_simulation", "05_commercial_heatmap"],
    "читаемост":        ["04_reader_simulation", "12_pacing_engine"],
    "вовлечени":        ["04_reader_simulation", "01_tension_curve"],
    "скучн":            ["04_reader_simulation", "12_pacing_engine"],
    "интерес":          ["04_reader_simulation"],

    # Голос
    "голос":            ["07_voice_consistency", "21_voice_constructor"],
    "стиль автора":     ["21_voice_constructor", "07_voice_consistency"],
    "единств":          ["07_voice_consistency"],
    "консистентн":      ["07_voice_consistency"],
}

# ─── Жанровые усилители ───────────────────────────────────────────────────────
# При определённом жанре некоторые модули получают приоритет

GENRE_BOOSTS: dict[str, list[str]] = {
    "detective":    ["13_foreshadowing_engine", "10_subtext_engine", "04_reader_simulation"],
    "noir":         ["25_style_transformations", "10_subtext_engine", "22_sensory_immersion"],
    "fantasy":      ["22_sensory_immersion", "08_world_state_kernel"],
    "horror":       ["01_tension_curve", "22_sensory_immersion", "25_style_transformations"],
    "romance":      ["17_character_chemistry", "11_micromoments_library", "02_character_resonance"],
    "thriller":     ["01_tension_curve", "20_stakes_escalation", "04_reader_simulation"],
    "realism":      ["11_micromoments_library", "09_deep_character_psychology", "14_narrative_distance"],
    "scifi":        ["22_sensory_immersion", "03_thematic_dna", "04_reader_simulation"],
}


def _normalize(text: str) -> str:
    """Нижний регистр, убираем знаки препинания."""
    import re
    return re.sub(r'[^\w\s]', ' ', text.lower())


def route_by_keywords(task_text: str, genre_key: str = "") -> tuple[list[str], int]:
    """
    Маршрутизация по ключевым словам без LLM.

    Возвращает (список_модулей, уверенность).
    Уверенность — количество уникальных совпавших ключей.
    """
    normalized = _normalize(task_text)
    hits: dict[str, int] = {}  # модуль → сколько раз выбран

    for keyword, modules in KEYWORD_ROUTES.items():
        if keyword in normalized:
            for m in modules:
                hits[m] = hits.get(m, 0) + 1

    # Жанровые усилители: +0.5 веса (через добавление в hits)
    genre_norm = genre_key.lower().split("_")[0] if genre_key else ""
    if genre_norm in GENRE_BOOSTS:
        for m in GENRE_BOOSTS[genre_norm]:
            # Добавляем только если уже есть хит или задача не слишком специфична
            if m in hits or len(hits) < 3:
                hits[m] = hits.get(m, 0) + 1

    # Сортировка по частоте
    sorted_modules = sorted(hits, key=lambda m: hits[m], reverse=True)

    # Берём топ-6, исключая BASE_MODULES (они добавятся отдельно)
    selected = [m for m in sorted_modules if m not in BASE_MODULES][:6]

    confidence = len(set(
        kw for kw in KEYWORD_ROUTES
        if kw in normalized
    ))

    return selected, confidence


def auto_route(task_text: str, genre_key: str = "",
               api_call_fn=None, confidence_threshold: int = 2) -> list[str]:
    """
    Полный роутер: сначала ключевые слова, потом LLM если нужно.

    confidence_threshold — минимум совпадений для доверия результату без LLM.
    Если api_call_fn не передан — всегда используем keyword routing.

    Возвращает финальный список модулей (BASE + выбранные).
    """
    keyword_result, confidence = route_by_keywords(task_text, genre_key)

    if confidence >= confidence_threshold or api_call_fn is None:
        # Достаточно уверены — LLM не нужен
        modules = list(BASE_MODULES)
        for m in keyword_result:
            if m not in modules:
                modules.append(m)
        return modules

    # Уверенность низкая — отдаём в LLM резолвер
    # Передаём keyword_result как подсказку чтобы сэкономить токены
    from .unified_engine import resolve_modules_dynamic
    return resolve_modules_dynamic(task_text, genre_key, api_call_fn)


def explain_routing(task_text: str, genre_key: str = "") -> str:
    """Отладочный вывод: почему выбраны эти модули."""
    normalized = _normalize(task_text)
    lines = [f"Задача: {task_text[:100]}", f"Жанр: {genre_key or 'не задан'}", ""]

    matched = {}
    for kw, modules in KEYWORD_ROUTES.items():
        if kw in normalized:
            matched[kw] = modules

    if matched:
        lines.append("Совпавшие ключевые слова:")
        for kw, mods in matched.items():
            lines.append(f"  '{kw}' → {', '.join(mods)}")
    else:
        lines.append("Ключевые слова не найдены → LLM резолвер")

    result, conf = route_by_keywords(task_text, genre_key)
    lines.append(f"\nУверенность: {conf}")
    lines.append(f"Выбранные модули: {result}")
    return "\n".join(lines)
