"""Свой порог у судьи, судья не видит балл критика, модули ремесла не всем писателям."""
from unittest.mock import patch

CRITIQUE = ("ГОЛОС: 6 — есть выразительные детали\nСТРУКТУРА: 5/10 — счёт без причины\n"
            "ПЕРСОНАЖИ: [7] — живые\nИТОГ: 27\n\nГЛАВНЫЕ ПРОБЛЕМЫ:\n- повтор; итого 27/50")


def test_judge_gets_critique_without_scores():
    from engine.pipeline_llm import critique_for_judge
    out = critique_for_judge(CRITIQUE)
    assert "27" not in out and "/10" not in out and "6 —" not in out
    assert "есть выразительные детали" in out and "счёт без причины" in out and "ГЛАВНЫЕ ПРОБЛЕМЫ" in out


def test_threshold_per_judge():
    from engine.pipeline_config import ACCEPT_TOTAL, accept_total_for, verdict_rule_for_prompt
    assert accept_total_for("chatgpt_subscription::gpt-6.1-sol@medium") == 30
    assert accept_total_for("claude_subscription::claude-sonnet-5-5") == 33
    assert accept_total_for("anthropic_direct::claude-haiku-4-5-20251001") == ACCEPT_TOTAL
    assert "ИТОГ ≥ 30" in verdict_rule_for_prompt("chatgpt_subscription::gpt-6.1-sol@medium")


def _judge(model, total, crit=7, gate="СВЯЗНОСТЬ: ОК — нет\n"):
    from engine.pipeline_steps import step_judge
    reply = (f"ГОЛОС: {crit}\nСТРУКТУРА: 7\nПЕРСОНАЖИ: 7\nСЦЕНЫ: 7\nДИАЛОГ: 7\nИТОГ: {total}\n"
             f"{gate}ВЕРДИКТ: НА ДОРАБОТКУ")
    seen = {}

    def call(m, system, user, **kw):
        seen["system"], seen["user"] = system, user
        return reply
    res = {"generated_text": "Глава. " * 300, "critique": CRITIQUE}
    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_judge(0, 1, 1, model, call, res)
    return res, seen


def test_verdict_follows_judge_threshold_not_model_word():
    sol = "chatgpt_subscription::gpt-6.1-sol@medium"
    res, seen = _judge(sol, 33)
    assert res["verdict"] == "ПРИНЯТЬ"                  # модель сказала «на доработку»
    assert "ИТОГ ≥ 30" in seen["system"] and "ИТОГ: 27" not in seen["user"]
    assert _judge(sol, 29)[0]["verdict"] == "НА ДОРАБОТКУ"
    assert _judge(sol, 40, crit=3)[0]["verdict"] == "НА ДОРАБОТКУ"   # провал критерия
    assert _judge("anthropic_direct::claude-haiku-4-5-20251001", 33)[0]["verdict"] == "НА ДОРАБОТКУ"
    # Строки вне балла нет в ответе — не проверено, а не «ОК» (разбор 21.10)
    res = _judge(sol, 40, gate="")[0]
    assert res["verdict"] == "НА ДОРАБОТКУ" and res["judge_gates_missing"] == ["СВЯЗНОСТЬ"]


def test_craft_modules_off_for_sol_only():
    from engine.pipeline_config import craft_modules_on
    assert not craft_modules_on("chatgpt_subscription::gpt-6.1-sol@medium")
    assert craft_modules_on("claude_subscription::claude-sonnet-5-5")
    assert craft_modules_on("nano_gpt::deepseek/deepseek-v4-pro")


def test_engine_block_without_modules_for_sol():
    from engine.unified_engine import build_engine_context
    task = "Глава 3. Сыщик допрашивает свидетеля в театре."
    with_mod = build_engine_context("детектив", "quality", "claude_subscription::claude-sonnet-5-5", task_text=task)
    without = build_engine_context("детектив", "quality", "chatgpt_subscription::gpt-6.1-sol@medium", task_text=task)
    assert len(without) < len(with_mod)
