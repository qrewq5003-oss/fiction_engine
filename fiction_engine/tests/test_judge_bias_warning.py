"""
Предупреждение, когда судья пристрастен к тексту генератора (замер 13.10:
Claude узнаёт текст Claude 16 раз из 16).
"""
from unittest.mock import patch


def test_model_family():
    from engine.pipeline_config import model_family
    assert model_family("claude_subscription::claude-sonnet-5-5") == "claude"
    assert model_family("anthropic_direct::claude-opus-5-5") == "claude"
    assert model_family("nano_gpt::anthropic/claude-sonnet-4.6") == "claude"
    assert model_family("nano_gpt::deepseek/deepseek-v4-pro-0813") == "deepseek"
    assert model_family("deepseek_direct::deepseek-chat") == "deepseek"
    assert model_family("nano_gpt::moonshotai/kimi-k2.5") == "kimi"
    assert model_family("nano_gpt::z-ai/glm-5.3") == "glm"


def test_warning_cases():
    """Любая семья: Claude не судит Claude, GPT не судит GPT (21.10 — было только про Claude)."""
    from engine.pipeline_config import judge_bias_warning
    assert "одной семьи" in judge_bias_warning("claude_subscription::claude-sonnet-5-5",
                                               "anthropic_direct::claude-opus-5-5")
    assert "одной семьи" in judge_bias_warning("chatgpt_subscription::gpt-6.1-sol@medium",
                                               "chatgpt_subscription::gpt-6.1-luna")
    assert "Kimi" not in judge_bias_warning("claude_subscription::claude-sonnet-5-5",
                                            "claude_subscription::claude-haiku-5-5")
    assert judge_bias_warning("claude_subscription::claude-sonnet-5-5",
                              "chatgpt_subscription::gpt-6.1-sol@medium") == ""
    assert judge_bias_warning("", "chatgpt_subscription::gpt-6.1-sol@medium") == ""


def test_same_family_judge_does_not_start(project_id):
    import pytest
    from engine import pipeline
    with pytest.raises(pipeline.SameFamilyJudge):
        pipeline.start_pipeline(project_id, 3, "задача", "claude_subscription::claude-sonnet-5-5",
                                "c", "e", "claude_subscription::claude-haiku-5-5")


def test_start_pipeline_without_warning_for_other_family(project_id):
    from engine import pipeline
    with patch.object(pipeline, "run_pipeline_step",
                      side_effect=lambda **kw: {"verdict": "ПРИНЯТЬ", "judge_score": 35, "generated_text": "т"}):
        res = pipeline.start_pipeline(project_id, 3, "задача", "claude_subscription::claude-sonnet-5-5",
                                      "m", "m", "chatgpt_subscription::gpt-6.1-sol@medium")
    assert "judge_warning" not in res
