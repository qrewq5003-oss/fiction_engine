"""
GPT через подписку ChatGPT (Codex CLI) — личный провайдер, выключен по умолчанию.
CLI не вызывается: subprocess подменён.
"""
import json
from unittest.mock import patch

import pytest


def _run(text="Дождь шёл всю ночь.", events=None, code=0):
    """Подмена subprocess.run: пишет ответ в файл -o, как codex exec."""
    evs = events if events is not None else [
        {"type": "thread.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
        {"type": "turn.completed", "usage": {"input_tokens": 9000, "output_tokens": 12}}]

    def fake(cmd, **kw):
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as f:
            f.write(text)

        class P:
            returncode = code
            stdout = "\n".join(json.dumps(e) for e in evs)
            stderr = ""
        fake.cmd, fake.kw = cmd, kw
        return P()
    return fake


def test_disabled_by_default(monkeypatch):
    from engine.api import get_all_models_flat
    from engine.db_settings import get_api_key
    monkeypatch.delenv("FE_CHATGPT_SUBSCRIPTION", raising=False)
    assert not any(m["provider"] == "chatgpt_subscription" for m in get_all_models_flat())
    assert get_api_key("chatgpt_subscription") is None


def test_enabled_calls_codex_read_only_without_tools(monkeypatch):
    from engine.api import call_model, get_last_usage
    monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "1")
    fake = _run()
    with patch("engine.api.shutil.which", return_value="/usr/bin/codex"), \
         patch("engine.api.subprocess.run", side_effect=fake):
        out = call_model("chatgpt_subscription::gpt-6.1-sol@high", "сис", "юзер")
    cmd = fake.cmd
    assert out == "Дождь шёл всю ночь."
    assert cmd[:2] == ["/usr/bin/codex", "exec"] and cmd[-1] == "-"
    assert cmd[cmd.index("-s") + 1] == "read-only" and cmd[cmd.index("-m") + 1] == "gpt-6.1-sol"
    assert "model_reasoning_effort=high" in cmd and "--ephemeral" in cmd and "--ignore-user-config" in cmd
    assert "shell_tool" in cmd and fake.kw["input"] == "юзер"
    assert get_last_usage()["input_tokens"] == 9000 and get_last_usage()["reported_cost"] == 0.0


def test_tool_call_is_an_error(monkeypatch):
    from engine.api import call_model
    monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "1")
    evs = [{"type": "item.completed", "item": {"type": "command_execution", "command": "dir"}},
           {"type": "turn.completed", "usage": {}}]
    with patch("engine.api.shutil.which", return_value="/usr/bin/codex"), \
         patch("engine.api.subprocess.run", side_effect=_run(events=evs)):
        with pytest.raises(RuntimeError, match="инструмент"):
            call_model("chatgpt_subscription::gpt-6-luna", "с", "у")


def test_turn_failed_raises(monkeypatch):
    from engine.api import call_model
    monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "1")
    evs = [{"type": "turn.failed", "error": {"message": "usage limit reached"}}]
    with patch("engine.api.shutil.which", return_value="/usr/bin/codex"), \
         patch("engine.api.subprocess.run", side_effect=_run(text="", events=evs, code=1)):
        with pytest.raises(RuntimeError, match="usage limit"):
            call_model("chatgpt_subscription::gpt-6-luna", "с", "у")


def test_prefill_glued_with_space(monkeypatch):
    from engine.api import call_model
    monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "1")
    with patch("engine.api.shutil.which", return_value="/usr/bin/codex"), \
         patch("engine.api.subprocess.run", side_effect=_run(text="а в щель тянуло.")):
        out = call_model("chatgpt_subscription::gpt-6-luna", "с", "у", prefill="Дождь стучал, и")
    assert out == "Дождь стучал, и а в щель тянуло."


def test_gpt_is_its_own_family():
    from engine.pipeline_config import judge_bias_warning, model_family
    assert model_family("chatgpt_subscription::gpt-6.1-sol@medium") == "gpt"
    assert judge_bias_warning("claude_subscription::claude-sonnet-5-5",
                              "chatgpt_subscription::gpt-6.1-sol@medium") == ""


def test_reconnect_then_completed_is_an_answer(monkeypatch):
    """«Reconnecting... 2/5» — промежуточное событие: ход дошёл, ответ не выбрасывается."""
    from engine.api import call_model
    monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "1")
    evs = [{"type": "thread.started"},
           {"type": "error", "message": "Reconnecting... 2/5 (stream disconnected before completion: tls handshake eof)"},
           {"type": "item.completed", "item": {"type": "agent_message", "text": "Ответ."}},
           {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]
    with patch("engine.api.shutil.which", return_value="/usr/bin/codex"), \
         patch("engine.api.subprocess.run", side_effect=_run(text="Ответ.", events=evs)):
        assert call_model("chatgpt_subscription::gpt-6-luna", "с", "у") == "Ответ."


def test_reconnect_without_completion_raises(monkeypatch):
    """Переподключения кончились, ход не завершён — ошибка с последним сообщением."""
    from engine.api import call_model
    monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "1")
    evs = [{"type": "error", "message": "Reconnecting... 5/5 (tls handshake eof)"},
           {"type": "turn.failed", "error": {"message": "stream disconnected"}}]
    with patch("engine.api.shutil.which", return_value="/usr/bin/codex"), \
         patch("engine.api.subprocess.run", side_effect=_run(text="", events=evs, code=1)):
        with pytest.raises(RuntimeError, match="stream disconnected"):
            call_model("chatgpt_subscription::gpt-6-luna", "с", "у")


def test_error_item_is_not_a_tool(monkeypatch):
    """item.type == "error" — сообщение codex о сбое, не вызов инструмента (18.10)."""
    from engine.api import call_model
    monkeypatch.setenv("FE_CHATGPT_SUBSCRIPTION", "1")
    evs = [{"type": "item.completed", "item": {"type": "error", "message": "Reconnecting... 2/5"}},
           {"type": "item.completed", "item": {"type": "agent_message", "text": "Ответ."}},
           {"type": "turn.completed", "usage": {}}]
    with patch("engine.api.shutil.which", return_value="/usr/bin/codex"),          patch("engine.api.subprocess.run", side_effect=_run(text="Ответ.", events=evs)):
        assert call_model("chatgpt_subscription::gpt-6-luna", "с", "у") == "Ответ."
