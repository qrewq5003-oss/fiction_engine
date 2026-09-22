#!/usr/bin/env python3
"""
Бюджет ответа должен доходить до модели.

`StepConfig("generate", max_tokens=PROSE_MAX_TOKENS)` объявлял бюджет
главы — 11730 токенов. При конверсии в PipelineStep он ТЕРЯЛСЯ:
`PipelineStep(s.name, s.enabled)` переносил имя и флаг, но не бюджет.
Шаговые функции зовут call_fn без max_tokens, поэтому действовало
умолчание call_model — 6000 токенов.

Поймано живым прогоном главы 22.09: Sonnet дважды выдал ровно 6000
токенов и оборвался на полуслове.

    WARNING: Глава оборвана: ответ упёрся в потолок max_tokens.
             Написано 2148 слов из ~3000.

6000 токенов русского текста — это около 2100 слов. Движок требовал
«СТРОГО 2500-3000 слов» и структурно не мог их получить: сколько ни
проси, ответ обрывался.

Это объясняет и давнее наблюдение, что модели «пишут меньше заказанного»:
часть недобора была не их, а наша.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())


@pytest.fixture
def budgets(monkeypatch):
    """Прогнать цикл и вернуть бюджет, с которым звали модель на каждом шаге."""
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "b.db")
    dbc.init_db()
    from engine.db import create_project
    from engine.db_narrative import create_pipeline_run
    import engine.pipeline as pipeline

    pid = create_project("Бюджет", "детектив")
    seen = []

    def fake(model_value, system, user, max_tokens=6000, prefill=""):
        low = (system or "").lower()
        # Роли различаются по системному промпту. Первая версия теста
        # искала «писатель», а движок говорит «Ты — автор … прозы»:
        # ни один вызов не опознавался, и тест проверял пустой список.
        # Поймала это проверка проверки («генератор не вызывался»).
        role = ("критик" if "строгий литературный редактор" in low else
                "судья" if "главный редактор" in low else
                "редактор" if "редактор и автор" in low else
                "генератор" if "автор" in low and "прозы" in low else "другой")
        seen.append((role, max_tokens))
        if role == "критик":
            return ("ГОЛОС: 6/10 — ок\nСТРУКТУРА: 6/10 — ок\nПЕРСОНАЖИ: 6/10 — ок\n"
                    "СЦЕНЫ: 6/10 — ок\nДИАЛОГ: 6/10 — ок\nИТОГ: 30/50")
        if role == "судья":
            return "ИТОГ: 30/50\nВЕРДИКТ: ПРИНЯТЬ"
        return "Текст главы. " * 300

    monkeypatch.setattr(pipeline, "_call", fake)
    run_id = create_pipeline_run(pid, 1, "m::m", "m::m", "m::m", "m::m")
    pipeline.run_pipeline_step(
        run_id=run_id, iteration=1, project_id=pid, chapter_num=1,
        generation_prompt="задача", model_gen="m::m", model_critic="m::m",
        model_editor="m::m", model_judge="m::m",
        steps=pipeline.PIPELINE_GENERATE_AND_EDIT)
    return seen


def test_generation_gets_the_prose_budget(budgets):
    from engine.pipeline_config import PROSE_MAX_TOKENS
    gen = [mt for role, mt in budgets if role == "генератор"]
    assert gen, "генератор не вызывался — тест не проверяет ничего"
    assert gen[0] == PROSE_MAX_TOKENS, (
        f"глава пишется с бюджетом {gen[0]} вместо {PROSE_MAX_TOKENS}: "
        "текст оборвётся на полуслове, не добрав требуемого объёма")


def test_budget_is_enough_for_the_demanded_volume():
    """
    Проверка связи, а не числа: бюджет должен покрывать объём, который
    требует промпт. Русский текст дорог в токенах.
    """
    from engine.pipeline_config import PROSE_MAX_TOKENS, TARGET_CHAPTER_WORDS
    # На главах проекта: около 6.8 символа на слово, около 2.5 символа на токен.
    need = TARGET_CHAPTER_WORDS * 6.8 / 2.5
    assert PROSE_MAX_TOKENS >= need, (
        f"бюджет {PROSE_MAX_TOKENS} мал для {TARGET_CHAPTER_WORDS} слов "
        f"(нужно около {need:.0f})")


def test_editor_gets_the_prose_budget_too(budgets):
    """Редактор возвращает всю главу целиком — ему нужен тот же бюджет."""
    from engine.pipeline_config import PROSE_MAX_TOKENS
    ed = [mt for role, mt in budgets if role == "редактор"]
    assert ed and ed[0] == PROSE_MAX_TOKENS


def test_short_steps_keep_small_budgets(budgets):
    """Критику и судье громадный бюджет не нужен — это были бы лишние деньги."""
    from engine.pipeline_config import PROSE_MAX_TOKENS
    for role, mt in budgets:
        if role in ("критик", "судья"):
            assert mt < PROSE_MAX_TOKENS


def test_step_config_budget_survives_conversion():
    """Само место, где бюджет терялся."""
    from engine.pipeline_config import StepConfig, PipelineConfig, PROSE_MAX_TOKENS
    cfg = PipelineConfig(steps=[StepConfig("generate", max_tokens=PROSE_MAX_TOKENS)])
    assert cfg.to_pipeline_steps()[0].max_tokens == PROSE_MAX_TOKENS


def test_usage_rows_name_their_step(monkeypatch):
    """
    Учёт должен говорить, на что ушли деньги.

    Без метки строки расхода анонимны, и разбор прогона превращается в
    гадание по числам: «вход 19956 — это редактура или генерация?». Я
    потратил на такое гадание отдельный заход, прежде чем сообразил
    прочитать pipeline_iterations.

    Метка ставится в контекст, а не передаётся аргументом call_fn: десятки
    тестов подменяют _call заглушками с фиксированной сигнатурой, и лишний
    параметр их ломает.
    """
    import tempfile
    from pathlib import Path
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "op.db")
    dbc.init_db()

    import engine.api as api
    import engine.pipeline as pipeline
    from engine.db import create_project
    from engine.db_narrative import create_pipeline_run

    seen = []
    monkeypatch.setattr(api, "_record_usage",
                        lambda p, m, op="": seen.append(op or api.get_current_operation()))

    def fake(model_value, system, user, max_tokens=6000, prefill=""):
        api._record_usage("p", "m")
        low = (system or "").lower()
        if "строгий литературный" in low:
            return ("ГОЛОС: 6/10 — ок\nСТРУКТУРА: 6/10 — ок\nПЕРСОНАЖИ: 6/10 — ок\n"
                    "СЦЕНЫ: 6/10 — ок\nДИАЛОГ: 6/10 — ок\nИТОГ: 30/50")
        if "главный редактор" in low:
            return "ИТОГ: 30/50\nВЕРДИКТ: ПРИНЯТЬ"
        return "Текст. " * 300

    monkeypatch.setattr(pipeline, "_call", fake)
    pid = create_project("Метки", "детектив")
    run_id = create_pipeline_run(pid, 1, "m::m", "m::m", "m::m", "m::m")
    pipeline.run_pipeline_step(
        run_id=run_id, iteration=1, project_id=pid, chapter_num=1,
        generation_prompt="з", model_gen="m::m", model_critic="m::m",
        model_editor="m::m", model_judge="m::m",
        steps=pipeline.PIPELINE_GENERATE_AND_EDIT)

    assert "generate" in seen and "critique" in seen and "edit" in seen and "judge" in seen, \
        f"строки расхода не названы по шагам: {seen}"
    assert "" not in seen, "есть безымянные строки расхода"
