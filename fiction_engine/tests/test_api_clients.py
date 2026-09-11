#!/usr/bin/env python3
"""
Клиенты провайдеров: разбор ответа, prefill, причина остановки, понижение
потолка. Перенесено из run_tests.py при слиянии наборов.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()


def _openai_response(text="ответ модели", finish="stop"):
    choice = MagicMock()
    choice.message.content = text
    choice.finish_reason = finish
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestOpenAICompatibleClients:
    @pytest.mark.parametrize("fn_name,key_env", [
        ("_call_openai_direct",   "OPENAI_API_KEY"),
        ("_call_gemini_direct",   "GEMINI_API_KEY"),
        ("_call_deepseek_direct", "DEEPSEEK_API_KEY"),
        ("_call_nanogpt",         "NANO_GPT_API_KEY"),
    ])
    def test_returns_message_content(self, fn_name, key_env):
        import engine.api as api
        with patch.object(api, "OpenAI") as client:
            client.return_value.chat.completions.create.return_value = _openai_response()
            out = getattr(api, fn_name)("модель", "система", "запрос", "ключ", 500)
        assert out == "ответ модели"

    def test_prefill_is_prepended(self):
        import engine.api as api
        with patch.object(api, "OpenAI") as client:
            client.return_value.chat.completions.create.return_value = \
                _openai_response(" и продолжение")
            out = api._call_openai_direct("м", "с", "з", "ключ", 500,
                                          prefill="Начало главы")
        assert out.startswith("Начало главы")

    def test_finish_reason_recorded(self):
        import engine.api as api
        with patch.object(api, "OpenAI") as client:
            client.return_value.chat.completions.create.return_value = \
                _openai_response(finish="length")
            api._call_openai_direct("м", "с", "з", "ключ", 500)
        assert api.get_last_stop_reason() == "length"

    def test_key_from_environment(self):
        import engine.api as api
        with patch.dict("os.environ", {"OPENAI_API_KEY": "из-окружения"}):
            with patch.object(api, "OpenAI") as client:
                client.return_value.chat.completions.create.return_value = _openai_response()
                api._call_openai_direct("м", "с", "з", None, 500)
                assert client.call_args.kwargs["api_key"] == "из-окружения"

    @pytest.mark.parametrize("fn_name,msg", [
        ("_call_openai_direct",   "OpenAI"),
        ("_call_gemini_direct",   "Gemini"),
        ("_call_deepseek_direct", "DeepSeek"),
        ("_call_nanogpt",         "nano"),
    ])
    def test_missing_key_raises(self, fn_name, msg):
        import engine.api as api
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError):
                getattr(api, fn_name)("м", "с", "з", None, 500)

    def test_prefill_adds_assistant_message(self):
        import engine.api as api
        with patch.object(api, "OpenAI") as client:
            client.return_value.chat.completions.create.return_value = _openai_response()
            api._call_openai_direct("м", "с", "з", "ключ", 500, prefill="хвост")
            messages = client.return_value.chat.completions.create.call_args.kwargs["messages"]
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == "хвост"


class TestReducedMaxTokens:
    @pytest.mark.parametrize("msg", [
        "max_tokens: must be <= 8192",
        "max output tokens exceeded",
        "maximum tokens for this model is 4096",
    ])
    def test_halves_on_output_limit(self, msg):
        from engine.api import _reduced_max_tokens
        assert _reduced_max_tokens(Exception(msg), 11730) == 5865

    def test_never_below_floor(self):
        from engine.api import _reduced_max_tokens
        assert _reduced_max_tokens(Exception("max_tokens too big"), 5000) == 4096

    def test_no_retry_when_already_at_floor(self):
        from engine.api import _reduced_max_tokens
        assert _reduced_max_tokens(Exception("max_tokens too big"), 4096) is None

    @pytest.mark.parametrize("msg", [
        "rate_limit_exceeded", "429 Too Many Requests", "quota exceeded",
        "invalid_api_key", "authentication failed", "permission denied",
        "This model's maximum context length is 8192 tokens",
        "Connection timeout",
    ])
    def test_no_retry_for_unrelated_failures(self, msg):
        from engine.api import _reduced_max_tokens
        assert _reduced_max_tokens(Exception(msg), 11730) is None


class TestParseModelValue:
    @pytest.mark.parametrize("value,provider,model", [
        ("anthropic_direct::claude-opus-4-6", "anthropic_direct", "claude-opus-4-6"),
        ("nano_gpt::anthropic/claude-opus-4.6", "nano_gpt", "anthropic/claude-opus-4.6"),
    ])
    def test_splits_provider_and_model(self, value, provider, model):
        from engine.api import parse_model_value
        assert parse_model_value(value) == (provider, model)

    def test_models_flat_shape(self):
        from engine.api import get_all_models_flat
        models = get_all_models_flat()
        assert models
        for m in models:
            assert {"value", "label", "provider", "model_id"} <= set(m)
            assert "::" in m["value"]
