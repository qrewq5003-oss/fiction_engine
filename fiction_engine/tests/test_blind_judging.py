#!/usr/bin/env python3
"""
Судья не должен знать, кем написан текст.

Что проверяется. В промпт критика и судьи не попадает ни имя модели, ни
провайдер, ни роль автора — только текст главы и задача. Проверка идёт по
всем вызовам цикла: перехватываем каждый и обыскиваем.

Чего проверка НЕ даёт, и это важнее. Скрытое имя не защищает от
самопредпочтения: модель узнаёт собственный слог. Замеры 15.09 —

    судья       верхние три                      свой текст
    Haiku 4.5   чужие модели                     место 5 из 15
    Kimi K2.5   свой текст первым                место 1 из 15
    GLM 5.3     своё семейство заняло 1, 2, 3    места 1 и 3

Завышали они, УЖЕ не зная автора явно: имени в промпте не было и тогда.
Поэтому единственная работающая мера — судья другой модели, чем
генератор. Она закреплена в DEFAULT_ROLE_MODELS и проверяется ниже.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

# Признаки, по которым судья мог бы опознать автора.
AUTHOR_MARKERS = ("claude", "sonnet", "haiku", "opus", "anthropic_direct",
                  "nano_gpt", "openai", "gpt-", "glm", "kimi", "deepseek",
                  "qwen", "llama", "mistral", "hermes")


@pytest.fixture
def captured(monkeypatch):
    """Прогнать цикл и вернуть промпты критика и судьи."""
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "blind.db")
    dbc.init_db()
    from engine.db import create_project
    from engine.db_narrative import create_pipeline_run
    import engine.pipeline as pipeline

    pid = create_project("Слепая оценка", "детектив")
    calls = []

    def fake(model_value, system, user, max_tokens=6000, prefill="", operation=""):
        calls.append({"system": system or "", "user": user or ""})
        low = (system or "").lower()
        if "критик" in low:
            return ("ГОЛОС: 6/10 — ок\nСТРУКТУРА: 6/10 — ок\nПЕРСОНАЖИ: 6/10 — ок\n"
                    "СЦЕНЫ: 6/10 — ок\nДИАЛОГ: 6/10 — ок\nИТОГ: 30/50")
        if "главный редактор" in low:
            return "ИТОГ: 30/50\nВЕРДИКТ: ПРИНЯТЬ"
        return "Текст главы. " * 300

    monkeypatch.setattr(pipeline, "_call", fake)
    gen = "anthropic_direct::claude-sonnet-5"
    judge = "openai_direct::gpt-4o"            # судья другой семьи, чем писатель
    run_id = create_pipeline_run(pid, 1, gen, judge, gen, judge)
    pipeline.run_pipeline_step(run_id=run_id, iteration=1, project_id=pid, chapter_num=1,
                               generation_prompt="задача", model_gen=gen,
                               model_critic=judge, model_editor=gen, model_judge=judge)
    return [c for c in calls
            if "критик" in c["system"].lower() or "главный редактор" in c["system"].lower()]


def test_critic_and_judge_were_actually_called(captured):
    """Проверка проверки: если перехват пуст, всё остальное ничего не значит."""
    assert captured, "ни критик, ни судья не вызывались — тест не проверяет ничего"


def test_no_author_identity_in_critic_and_judge_prompts(captured):
    for call in captured:
        blob = (call["system"] + "\n" + call["user"]).lower()
        found = sorted({m for m in AUTHOR_MARKERS if m in blob})
        assert not found, f"судья видит, кем написан текст: {found}"


def test_judge_differs_from_generator_by_default():
    """
    Единственная мера, которая действительно работает против
    самопредпочтения. Скрытое имя — не работает.
    """
    from engine.pipeline_config import DEFAULT_ROLE_MODELS
    assert DEFAULT_ROLE_MODELS["judge"] != DEFAULT_ROLE_MODELS["gen"], (
        "судья и генератор — одна модель: она завысит оценку своему слогу")


def test_judge_default_is_the_calibrated_one():
    from engine.pipeline_config import DEFAULT_ROLE_MODELS, CALIBRATED_JUDGE
    assert DEFAULT_ROLE_MODELS["judge"] == CALIBRATED_JUDGE, (
        "судья по умолчанию не тот, на котором калиброван порог")


def test_all_roles_have_a_default():
    from engine.pipeline_config import DEFAULT_ROLE_MODELS
    assert set(DEFAULT_ROLE_MODELS) == {"gen", "critic", "editor", "judge"}
    assert all("::" in v for v in DEFAULT_ROLE_MODELS.values())


def test_writer_by_subscription_when_enabled(monkeypatch):
    from unittest.mock import patch
    from engine.pipeline_config import DEFAULT_ROLE_MODELS, default_role_models
    monkeypatch.delenv("FE_CLAUDE_SUBSCRIPTION", raising=False)
    monkeypatch.delenv("FE_CHATGPT_SUBSCRIPTION", raising=False)
    assert default_role_models() == DEFAULT_ROLE_MODELS
    # Подписка считается включённой только при установленном CLI — в CI его нет
    with patch("engine.api.shutil.which", return_value="/usr/bin/cli"):
        monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "1")
        assert default_role_models()["gen"] == "chatgpt_subscription::gpt-6.1-sol@medium"
        monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
        got = default_role_models()
    assert got["gen"] == "claude_subscription::claude-sonnet-5-5"
    # Судья — подписка другого семейства, редактор — писатель
    assert got["judge"] == "chatgpt_subscription::gpt-6.1-sol@medium"
    assert got["editor"] == got["gen"]


def test_roles_never_judge_own_family_and_critic_is_not_judge(monkeypatch):
    from unittest.mock import patch
    from engine.pipeline_config import CRITIC_FALLBACK, CRITIC_MODEL, default_role_models, model_family
    monkeypatch.setenv("NANO_GPT_API_KEY", "k")
    with patch("engine.api.shutil.which", return_value="/usr/bin/cli"):
        for claude, gpt in (("1", "1"), ("0", "1"), ("1", "0")):
            monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", claude)
            monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", gpt)
            r = default_role_models()
            assert model_family(r["judge"]) != model_family(r["gen"]) or claude + gpt != "11", r
            # Критик Haiku — по подписке Claude; без неё Luna (не nano), не судья
            assert r["critic"] == (CRITIC_MODEL if claude == "1" else CRITIC_FALLBACK) and r["critic"] != r["judge"]


def test_role_presets_never_judge_own_family():
    """В обоих наборах судья, проверяющий и оценщик — не семья писателя."""
    from engine.pipeline_config import ROLE_PRESETS, model_family
    for name, p in ROLE_PRESETS.items():
        writer = model_family(p["roles"]["gen"])
        for m in (p["roles"]["judge"], p["settings"]["continuity_model"], p["settings"]["scorer_model"]):
            assert model_family(m) != writer, (name, m)
        assert p["roles"]["critic"] != p["roles"]["judge"]
        assert p["roles"]["editor"] == p["roles"]["gen"]


def test_apply_preset_sets_settings_and_defaults(project_id, monkeypatch):
    from unittest.mock import patch
    from engine.db import get_setting
    from web.app import app
    from engine.pipeline_config import ROLE_PRESETS, default_role_models
    monkeypatch.setenv("NANO_GPT_API_KEY", "k")
    app.config.update(TESTING=True, FE_CSRF=False)
    with patch("engine.api.shutil.which", return_value="/usr/bin/cli"):
        monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
        monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "1")
        r = app.test_client().post("/pipeline/preset", json={"name": "gpt"}).get_json()
        assert r["ok"] and r["missing"] == []
        assert default_role_models() == ROLE_PRESETS["gpt"]["roles"]
    for key, model in ROLE_PRESETS["gpt"]["settings"].items():
        assert get_setting(key) == model
    assert app.test_client().post("/pipeline/preset", json={"name": "x"}).status_code == 400
