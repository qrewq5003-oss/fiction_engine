"""Выбор модели для кнопок без своего списка моделей и для вспомогательных вызовов."""


def test_resolver_without_key_falls_back(project_id, monkeypatch):
    """«Модель анализа задачи» без ключа: L3 и подбор модулей падали на «Нет API ключа»."""
    from engine.db import set_setting
    from engine.pipeline_llm import _get_resolver_model
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("NANO_GPT_API_KEY", "k")
    set_setting("resolver_model", "anthropic_direct::claude-haiku-4-5-20251001")
    assert _get_resolver_model("nano_gpt::x/y") == "nano_gpt::x/y"
    set_setting("resolver_model", "nano_gpt::cheap/one")
    assert _get_resolver_model("nano_gpt::x/y") == "nano_gpt::cheap/one"


def test_page_model_order(project_id, monkeypatch):
    from engine.db import set_setting
    from web.blueprints.helpers import page_model
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("NANO_GPT_API_KEY", "k")
    set_setting("continuity_model", "anthropic_direct::claude-sonnet-4-6")   # без ключа
    set_setting("last_model", "nano_gpt::last/one")
    assert page_model("nano_gpt::asked/one", "continuity_model") == "nano_gpt::asked/one"
    assert page_model("", "continuity_model") == "nano_gpt::last/one"
    set_setting("continuity_model", "nano_gpt::check/one")
    assert page_model("", "continuity_model") == "nano_gpt::check/one"


def test_l3_uses_its_own_model(project_id, monkeypatch):
    """L3 пишет «модель L3-саммари», а не лёгкая модель анализа задачи."""
    from unittest.mock import patch
    from engine.db import set_setting
    from engine.pipeline import generate_l3
    monkeypatch.setenv("NANO_GPT_API_KEY", "k")
    set_setting("resolver_model", "nano_gpt::light/one")
    set_setting("l3_model", "nano_gpt::strong/one")
    seen = []

    def fake(model, system, user, **kw):
        seen.append(model)
        return '{"events": "Команда погибла.", "characters": "", "conflicts": "", "promises": [], "mood": "мрак"}'
    with patch("engine.pipeline._call", side_effect=fake):
        generate_l3(project_id, 1, "Текст главы. " * 200, "nano_gpt::writer/one")
    assert seen and set(seen) == {"nano_gpt::strong/one"}
    set_setting("l3_model", "")
    seen.clear()
    with patch("engine.pipeline._call", side_effect=fake):
        generate_l3(project_id, 1, "Текст главы. " * 200, "nano_gpt::writer/one")
    assert set(seen) == {"nano_gpt::light/one"}


def test_l3_and_analysis_see_the_middle_of_a_long_chapter(project_id):
    """Середина главы (гибель команды) не выпадает: было 6000 + хвост 1500 символов."""
    from engine.l3_memory import generate_l3_summary
    from engine.chapter_analyzer import ChapterAnalyzer
    text = "Начало. " * 1500 + "ПОГИБЛИ ВСЕ ДВЕНАДЦАТЬ. " + "Конец. " * 1500   # ~22 тыс. символов
    prompts = []

    def fake(prompt):
        prompts.append(prompt)
        return '{"events": "e", "characters": "", "conflicts": "", "promises": [], "mood": "m"}'
    generate_l3_summary(project_id, 1, text, fake)
    ChapterAnalyzer().analyze(project_id, 1, text, fake)
    assert len(prompts) >= 2 and all("ПОГИБЛИ ВСЕ ДВЕНАДЦАТЬ" in p for p in prompts)
