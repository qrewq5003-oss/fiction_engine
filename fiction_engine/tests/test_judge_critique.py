"""Судье Sonnet разбор критика не передаётся; Sol его получает (bench/critic-no-nano-2026-10-18.json)."""
from unittest.mock import patch

SOL = "chatgpt_subscription::gpt-6.1-sol@medium"
SONNET = "claude_subscription::claude-sonnet-5-5"


def test_judge_sees_critique():
    from engine.pipeline_config import judge_sees_critique
    assert judge_sees_critique(SOL) and not judge_sees_critique(SONNET)


def test_critic_is_not_nano():
    from engine.pipeline_config import CRITIC_MODEL, ROLE_PRESETS
    assert not CRITIC_MODEL.startswith("nano_gpt")
    assert all(not m.startswith("nano_gpt") for p in ROLE_PRESETS.values()
               for m in [*p["roles"].values(), *p["settings"].values()])


def _judge_prompt(model_judge):
    from engine.pipeline_steps import step_judge
    seen = []
    results = {"generated_text": "Текст главы.", "critique": "ГОЛОС: 7 — штампы в диалоге\nИТОГ: 35"}
    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_judge(1, 1, 1, model_judge, lambda m, s, p, **kw: seen.append(p) or "ИТОГ: 30", results)
    return seen[0]


def test_sonnet_judges_without_critique(project_id):
    from engine.pipeline_steps import NO_CRITIQUE_FOR_JUDGE
    p = _judge_prompt(SONNET)
    assert NO_CRITIQUE_FOR_JUDGE in p and "штампы в диалоге" not in p


def test_sol_gets_critique_without_score(project_id):
    p = _judge_prompt(SOL)
    assert "штампы в диалоге" in p and "35" not in p
