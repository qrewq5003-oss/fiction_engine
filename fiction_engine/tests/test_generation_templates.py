"""
Шаблоны «Генерации», заметка после главы, пиковые финалы — разбор формулировок
26.10, пакет 27.10.
"""
import re

PLAN = ("ПЛАН ГЛАВЫ 3\n\nСЦЕНА 1: Причал\n  Вера встречает Лукаша у трапа\n\n"
        "СЦЕНА 2: Каюта\n  Лукаш отдаёт ей ключ")
MODES = ("quick", "quality", "master")


def _state(project_id):
    from engine.db_state import update_state
    update_state(project_id,
                 global_state=("## ПЕРСОНАЖИ\n\n### Зыков\nСОСТОЯНИЕ: убит\n\n### Марина\nСОСТОЯНИЕ: спит\n\n"
                               "### Глеб\nСОСТОЯНИЕ: пьян\n\n### Тамара\nСОСТОЯНИЕ: ждёт\n\n"
                               "### Вера\nСОСТОЯНИЕ: устала\n\n### Лукаш\nСОСТОЯНИЕ: молчит\n"),
                 plot_matrix="СТАТУС: активна\n", memory_graph="")


def _prompts(project_id):
    from engine.db_projects import get_project
    from engine.state_prompts import build_prompt
    return {m: build_prompt(project_id, 3, m, get_project(project_id)) for m in MODES}


def test_plan_replaces_scene_skeleton_and_finale_menu(project_id):
    """С планом со сценами скелет «СЦЕНА 1 […]» и меню финала не выводятся."""
    from engine.db import save_director_note
    _state(project_id)
    for mode, text in _prompts(project_id).items():
        assert "Последняя строка: [" in text or "ЗАКАНЧИВАЕТСЯ НА: [" in text or "Финал главы: [" in text, mode
    save_director_note(project_id, 2, PLAN)
    for mode, text in _prompts(project_id).items():
        assert "Причал" in text, mode
        assert not re.search(r"СЦЕНА \d[^\n]*\[~", text), mode
        assert "ЗАКАНЧИВАЕТСЯ НА: [" not in text and "Финал главы: [" not in text, mode


def test_characters_from_plan_first(project_id):
    """«Персонажи в этой главе» — названные в плане, а не первые четыре State."""
    from engine.db import save_director_note
    _state(project_id)
    save_director_note(project_id, 2, PLAN)
    text = _prompts(project_id)["quick"]
    block = text.split("ПЕРСОНАЖИ В ЭТОЙ ГЛАВЕ:")[1].split("\n\n")[0]
    assert "Вера" in block and "Лукаш" in block and "Зыков" not in block


def test_no_pressure_and_contradictions(project_id):
    """Без «провала задания», «высокого стандарта», подписи режима, клиффхэнгера,
    чисел частей главы и «по этому тебя оценивают»."""
    _state(project_id)
    for mode, text in _prompts(project_id).items():
        for gone in ("провал", "Высокий стандарт", "Высший стандарт", "# Режим:", "клиффхэнгер",
                     "ЖЁСТКИЕ ЗАПРЕТЫ", "все лгут", "по этому тебя оценивают", "Крюк [", "Вход ["):
            assert gone not in text, (mode, gone)
        assert text.count("ДЕТАЛИ ДОЛЖНЫ ДЕЙСТВОВАТЬ") == 1, mode


def test_tone_section_comes_with_its_rhythm_note(project_id):
    """Строка ритма тона отсылает к разделу «ТОН ГЛАВЫ» — он теперь в промпте."""
    from engine.db import set_chapter_tone
    from engine.genre_mix import CHAPTER_TONE_HEADER, MODIFIERS
    tone = next(k for k, v in MODIFIERS.items() if v.get("chapter") and v.get("rhythm"))
    set_chapter_tone(project_id, 3, tone)
    text = _prompts(project_id)["quick"]
    assert "«ТОН ГЛАВЫ»" in text and CHAPTER_TONE_HEADER in text


def test_peak_finale_examples_keep_author_dash_rule():
    """Примеры пиковых финалов — без длинного тире в авторской речи (правило автора)."""
    from engine.peak_finales import PEAK_FINALES
    from engine.text_signals import narration_dashes
    assert sum(len(narration_dashes(v["example"])) for v in PEAK_FINALES.values()) == 0


def test_director_note_prompt_does_not_prescribe_next_chapter():
    from engine.director_note import PROMPT
    assert "тон, темп" not in PROMPT and "разрядка" not in PROMPT
    assert "оборвалась" in PROMPT


def test_extension_prompt_has_no_unchecked_diagnosis():
    from engine.pipeline_config import extension_prompt
    assert "Сцены сжаты" not in extension_prompt("слово " * 1500)
