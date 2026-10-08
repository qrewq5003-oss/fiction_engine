"""
Claude через подписку Claude Code — личный провайдер, выключен по умолчанию.
CLI не вызывается: subprocess подменён.
"""
import json
from unittest.mock import patch

import pytest


def _proc(payload, code=0):
    class P:
        returncode = code
        stdout = json.dumps(payload)
        stderr = ""
    return P()


OK = {"is_error": False, "result": "Дождь шёл всю ночь.", "stop_reason": "end_turn",
      "usage": {"input_tokens": 2, "cache_creation_input_tokens": 600, "output_tokens": 9}}


def test_disabled_by_default(monkeypatch):
    from engine.api import get_all_models_flat
    from engine.db_settings import get_api_key
    monkeypatch.delenv("FE_CLAUDE_SUBSCRIPTION", raising=False)
    assert not any(m["provider"] == "claude_subscription" for m in get_all_models_flat())
    assert get_api_key("claude_subscription") is None


def test_enabled_calls_cli_without_tools_and_settings(monkeypatch):
    from engine.api import call_model, get_last_stop_reason, get_last_usage
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"), \
         patch("engine.api.subprocess.run", return_value=_proc(OK)) as run:
        out = call_model("claude_subscription::claude-sonnet-5-5", "сис", "юзер", max_tokens=300)
    cmd = run.call_args.args[0]
    assert out == "Дождь шёл всю ночь." and get_last_stop_reason() == "end_turn"
    assert cmd[:2] == ["claude", "-p"] and "--tools" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert "--setting-sources" in cmd and "--no-session-persistence" in cmd
    assert run.call_args.kwargs["input"] == "юзер"
    assert run.call_args.kwargs["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "300"
    assert get_last_usage()["reported_cost"] == 0.0


def test_prefill_glued_with_space(monkeypatch):
    from engine.api import call_model
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"), \
         patch("engine.api.subprocess.run", return_value=_proc(dict(OK, result="а в щель тянуло."))):
        out = call_model("claude_subscription::claude-haiku-4-5-20251001", "с", "у", prefill="Дождь стучал, и")
    assert out == "Дождь стучал, и а в щель тянуло."


def test_cli_error_raises(monkeypatch):
    from engine.api import call_model
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"), \
         patch("engine.api.subprocess.run", return_value=_proc({"is_error": True, "result": "limit"})):
        with pytest.raises(RuntimeError, match="limit"):
            call_model("claude_subscription::claude-sonnet-5-5", "с", "у")


def test_setup_token_from_settings_goes_to_cli_env(monkeypatch):
    """Токен `claude setup-token`, сохранённый в настройках, уходит CLI в окружении."""
    from engine.api import call_model
    from engine.db import save_api_key
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    save_api_key("claude_subscription", "sk-ant-oat01-test-token-0000")
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"), \
         patch("engine.api.subprocess.run", return_value=_proc(OK)) as run:
        call_model("claude_subscription::claude-sonnet-5-5", "с", "у")
    assert run.call_args.kwargs["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-test-token-0000"


def test_without_token_cli_login_is_used(monkeypatch):
    from engine.api import call_model
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"), \
         patch("engine.api.subprocess.run", return_value=_proc(OK)) as run:
        call_model("claude_subscription::claude-sonnet-5-5", "с", "у")
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in run.call_args.kwargs["env"]


def test_settings_card_only_when_enabled(monkeypatch):
    import logging
    from web.app import app
    app.config["TESTING"] = True
    logging.disable(logging.CRITICAL)
    client = app.test_client()
    monkeypatch.delenv("FE_CLAUDE_SUBSCRIPTION", raising=False)
    assert "claude setup-token" not in client.get("/settings").get_data(as_text=True)
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"), \
         patch("engine.api.claude_cli_logged_in", return_value=True):
        page = client.get("/settings").get_data(as_text=True)
    assert "claude setup-token" in page and "сейчас он есть" in page
    logging.disable(logging.NOTSET)
