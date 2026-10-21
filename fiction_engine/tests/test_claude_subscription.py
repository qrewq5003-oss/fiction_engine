"""
Claude через подписку Claude Code — личный провайдер, выключен по умолчанию.
CLI не вызывается: subprocess подменён.
"""
import json
from unittest.mock import patch

import pytest


def _proc(payload, code=0, turns=None):
    """Вывод `claude -p --output-format stream-json`: сообщения модели и итог result.
    turns — тексты сообщений модели по порядку (по умолчанию — один, как result)."""
    texts = turns if turns is not None else ([payload["result"]] if not payload.get("is_error") else [])
    lines = [{"type": "system", "subtype": "init"}]
    for i, t in enumerate(texts):
        if i:
            lines.append({"type": "user", "message": {"content": [{"type": "text",
                          "text": "Output token limit hit. Resume directly"}]}})
        lines.append({"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}})
    lines.append(dict(payload, type="result"))

    class P:
        returncode = code
        stdout = "\n".join(json.dumps(x, ensure_ascii=False) for x in lines)
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
    assert cmd[:2] == ["/usr/bin/claude", "-p"] and "--tools" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert "--setting-sources" in cmd and "--no-session-persistence" in cmd
    assert run.call_args.kwargs["input"] == "юзер"
    # Не меньше CLAUDE_SUB_MIN_OUTPUT: иначе CLI режет ответ и продолжает с шва
    assert run.call_args.kwargs["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "32000"
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
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"):
        page = client.get("/settings").get_data(as_text=True)
    assert "claude setup-token" in page
    logging.disable(logging.NOTSET)


def test_continuation_after_output_limit_keeps_the_beginning(monkeypatch):
    """CLI упёрся в лимит вывода и сам продолжил: result — только последнее
    сообщение, а глава — всё подряд (раньше начало терялось: «ень.»)."""
    from engine.api import call_model
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
    out_payload = dict(OK, result="ень. Холод пошёл через рубашку.")
    turns = ["Лукаш нырнул под мост. Наступила т", "ень. Холод пошёл через рубашку."]
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"), \
         patch("engine.api.subprocess.run", return_value=_proc(out_payload, turns=turns)) as run:
        out = call_model("claude_subscription::claude-sonnet-5-5", "с", "у")
    assert out == "Лукаш нырнул под мост. Наступила тень. Холод пошёл через рубашку."
    cmd = run.call_args.args[0]
    assert cmd[cmd.index("--output-format") + 1] == "stream-json" and "--verbose" in cmd


def test_output_limit_exhausted_returns_text_as_cut(monkeypatch):
    """Продолжения кончились: написанное возвращается, причина — max_tokens (обрыв)."""
    from engine.api import call_model, get_last_stop_reason
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
    err = {"is_error": True, "api_error": "max_output_tokens", "stop_reason": "stop_sequence",
           "result": "API Error: Claude's response exceeded the output token maximum."}
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"), \
         patch("engine.api.subprocess.run", return_value=_proc(err, turns=["Первая часть ", "вторая часть"])):
        out = call_model("claude_subscription::claude-sonnet-5-5", "с", "у")
    assert out == "Первая часть вторая часть" and get_last_stop_reason() == "max_tokens"


def test_old_single_json_output_still_parsed():
    from engine.api import _parse_claude_stream
    text, final = _parse_claude_stream(json.dumps(OK, ensure_ascii=False))
    assert text == "Дождь шёл всю ночь." and final["stop_reason"] == "end_turn"


def test_cli_runs_outside_repo_without_dev_memory(monkeypatch):
    """CLI из папки приложения подхватывал авто-память Claude Code разработчика (MEMORY.md):
    Haiku-критик «Фона» ссылался на «правило автора из памяти» и раз отказался оценивать (21.10)."""
    from pathlib import Path
    from engine.api import call_model
    monkeypatch.setenv("FE_CLAUDE_SUBSCRIPTION", "1")
    with patch("engine.api.shutil.which", return_value="/usr/bin/claude"), \
         patch("engine.api.subprocess.run", return_value=_proc(OK)) as run:
        call_model("claude_subscription::claude-haiku-5-5", "сис", "юзер", max_tokens=300)
    cwd = Path(run.call_args.kwargs["cwd"]).resolve()
    repo = Path(__file__).resolve().parents[2]
    assert cwd.is_dir() and repo not in (cwd, *cwd.parents)
    assert not any((d / ".git").exists() for d in (cwd, *cwd.parents))
