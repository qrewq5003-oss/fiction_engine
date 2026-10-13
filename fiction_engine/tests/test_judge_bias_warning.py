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
    from engine.pipeline_config import judge_bias_warning
    assert "оба Claude" in judge_bias_warning("claude_subscription::claude-sonnet-5-5",
                                              "anthropic_direct::claude-opus-5-5")
    assert "та же модель" in judge_bias_warning("nano_gpt::z-ai/glm-5.3", "nano_gpt::z-ai/glm-5.3")
    # Разные модели одного семейства, кроме Claude, — не узнают свой текст (6 из 16)
    assert judge_bias_warning("nano_gpt::deepseek/deepseek-v4-pro-0813",
                              "deepseek_direct::deepseek-chat") == ""
    assert judge_bias_warning("claude_subscription::claude-sonnet-5-5",
                              "nano_gpt::moonshotai/kimi-k2.5") == ""
    assert judge_bias_warning("", "nano_gpt::moonshotai/kimi-k2.5") == ""


def test_start_pipeline_returns_warning_after_auto_cycle(project_id):
    from engine import pipeline
    from engine.pipeline_config import AUTO_IMPROVE
    calls = []

    def fake_step(**kw):
        calls.append(1)
        return {"verdict": "НА ДОРАБОТКУ", "judge_score": len(calls), "generated_text": "т"}
    with patch.object(pipeline, "run_pipeline_step", side_effect=fake_step):
        res = pipeline.start_pipeline(project_id, 3, "задача", "claude_subscription::claude-sonnet-5-5",
                                      "m", "m", "claude_subscription::claude-sonnet-5-5", config=AUTO_IMPROVE)
    assert len(calls) > 1, "авто-цикл не сработал — тест не про то"
    assert "оба Claude" in res["judge_warning"]
    with patch.object(pipeline, "run_pipeline_step", side_effect=fake_step):
        res = pipeline.start_pipeline(project_id, 3, "задача", "claude_subscription::claude-sonnet-5-5",
                                      "m", "m", "nano_gpt::moonshotai/kimi-k2.5")
    assert "judge_warning" not in res
