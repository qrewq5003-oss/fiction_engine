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
