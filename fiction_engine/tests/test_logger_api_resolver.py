#!/usr/bin/env python3
"""
Логгер, клиенты API, динамический выбор модулей и пре-валидация.

Ветки, покрытые только автономным раннером: 36 строк logger, 26
unified_engine, 22 prevalidation, 21 api. Перенесено при слиянии наборов.
"""

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()


def _record(name="engine.pipeline", level=logging.ERROR, msg="сообщение", **extra):
    r = logging.LogRecord(name, level, "f.py", 1, msg, None, None)
    r.__dict__.update(extra)
    return r


# ─── StructuredFormatter ──────────────────────────────────────────────────────

class TestStructuredFormatter:
    def test_basic_shape(self):
        from engine.logger import StructuredFormatter
        out = StructuredFormatter().format(_record())
        assert "|" in out and "сообщение" in out
        assert "pipeline" in out

    def test_context_fields_rendered(self):
        from engine.logger import StructuredFormatter
        out = StructuredFormatter().format(
            _record(project_id=7, chapter_num=3, model="opus", reason="timeout"))
        for expected in ("project_id=7", "chapter_num=3", "model=opus", "reason=timeout"):
            assert expected in out

    def test_absent_fields_omitted(self):
        from engine.logger import StructuredFormatter
        out = StructuredFormatter().format(_record())
        assert "project_id=" not in out

    def test_long_module_name_truncated(self):
        from engine.logger import StructuredFormatter
        out = StructuredFormatter().format(_record(name="engine.очень_длинное_имя_модуля_сверх_меры"))
        assert "сообщение" in out

    @pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO,
                                       logging.WARNING, logging.ERROR])
    def test_all_levels(self, level):
        from engine.logger import StructuredFormatter
        assert StructuredFormatter().format(_record(level=level))

    def test_exception_is_formatted(self):
        from engine.logger import StructuredFormatter
        try:
            raise ValueError("внутри")
        except ValueError:
            rec = logging.LogRecord("engine.x", logging.ERROR, "f", 1,
                                    "с исключением", None, sys.exc_info())
        out = StructuredFormatter().format(rec)
        assert "с исключением" in out


# ─── DBHandler ────────────────────────────────────────────────────────────────

class TestDBHandler:
    def _rows(self):
        from engine.db_core import get_conn
        with get_conn() as c:
            return c.execute("SELECT context, error FROM engine_error_log").fetchall()

    def test_writes_plain_record(self, project_id):
        from engine.logger import DBHandler
        DBHandler().emit(_record(msg="без исключения"))
        assert any("без исключения" in r["error"] for r in self._rows())

    def test_writes_record_with_exception(self, project_id):
        """
        Раньше здесь падал AttributeError: formatException живёт на
        Formatter, а не на Handler. Его глотал except, и запись НЕ
        доходила до таблицы именно когда логируется исключение.
        """
        from engine.logger import DBHandler
        try:
            raise RuntimeError("настоящая ошибка")
        except RuntimeError:
            rec = logging.LogRecord("engine.x", logging.ERROR, "f", 1,
                                    "с исключением", None, sys.exc_info())
        DBHandler().emit(rec)
        rows = [r for r in self._rows() if "с исключением" in r["error"]]
        assert rows, "запись с исключением не попала в engine_error_log"
        assert "Traceback" in rows[0]["error"]

    def test_context_keeps_module_name_intact(self, project_id):
        """rstrip(набор) раньше отгрызал хвост имени: engine.state → engine.sta."""
        from engine.logger import DBHandler
        DBHandler().emit(_record(name="engine.state", msg="проверка имени"))
        rows = [r for r in self._rows() if "проверка имени" in r["error"]]
        assert rows and rows[0]["context"] == "engine.state"

    def test_never_raises_when_db_is_gone(self):
        from engine.logger import DBHandler
        with patch("engine.db_core.get_conn", side_effect=Exception("БД недоступна")):
            DBHandler().emit(_record())          # не должно бросить


# ─── Клиенты API ──────────────────────────────────────────────────────────────

class TestCallModel:
    def test_dispatches_to_provider(self):
        from engine.api import call_model
        with patch("engine.api._call_anthropic", return_value="ответ") as m:
            out = call_model("anthropic_direct::claude", "sys", "user",
                             anthropic_key="k", max_tokens=100)
        assert out == "ответ" and m.called

    def test_unknown_provider_raises(self):
        from engine.api import call_model
        with pytest.raises(ValueError, match="Неизвестный провайдер"):
            call_model("нет_такого::модель", "sys", "user")

    @pytest.mark.parametrize("provider,fn", [
        ("openai_direct",   "_call_openai_direct"),
        ("gemini_direct",   "_call_gemini_direct"),
        ("deepseek_direct", "_call_deepseek_direct"),
        ("nano_gpt",        "_call_nanogpt"),
    ])
    def test_every_provider_reachable(self, provider, fn):
        from engine.api import call_model
        with patch(f"engine.api.{fn}", return_value="ок") as m:
            assert call_model(f"{provider}::m", "s", "u", openai_key="k",
                              gemini_key="k", deepseek_key="k", nano_key="k") == "ок"
        assert m.called

    def test_stop_reason_recorded(self):
        from engine.api import call_model, get_last_stop_reason

        class Resp:
            stop_reason = "max_tokens"
            content = [type("C", (), {"text": "текст"})()]

        with patch("engine.api.anthropic") as a:
            a.Anthropic.return_value.messages.create.return_value = Resp()
            call_model("anthropic_direct::claude", "s", "u", anthropic_key="k")
        assert get_last_stop_reason() == "max_tokens"

    def test_missing_key_raises(self):
        from engine.api import call_model
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ключ"):
                call_model("anthropic_direct::claude", "s", "u")


# ─── Динамический выбор модулей ───────────────────────────────────────────────

class TestResolveModulesDynamic:
    def test_uses_model_answer(self):
        from engine.unified_engine import resolve_modules_dynamic
        out = resolve_modules_dynamic(
            "сцена погони", "thriller_spy",
            lambda prompt: '{"modules": ["12_pacing_engine", "20_stakes_escalation"]}')
        assert isinstance(out, list) and out

    def test_falls_back_on_garbage(self):
        from engine.unified_engine import resolve_modules_dynamic
        out = resolve_modules_dynamic("сцена", "fantasy_epic",
                                      lambda prompt: "не json вовсе")
        assert isinstance(out, list) and out, "должен остаться базовый набор"

    def test_falls_back_when_model_fails(self):
        from engine.unified_engine import resolve_modules_dynamic
        def boom(prompt): raise RuntimeError("API упал")
        assert isinstance(resolve_modules_dynamic("сцена", "horror_gothic", boom), list)

    def test_no_caller_returns_base(self):
        from engine.unified_engine import resolve_modules_dynamic
        assert isinstance(resolve_modules_dynamic("сцена", "detective_classic", None), list)


# ─── Пре-валидация ────────────────────────────────────────────────────────────

class TestPrevalidation:
    def test_contradictions_parsed(self, project_id):
        from engine.prevalidation import _check_state_contradictions
        answer = '{"blocking": [{"issue": "Марк мёртв", "detail": "погиб в гл.2"}]}'
        with patch("engine.prevalidation.call_model", return_value=answer):
            out = _check_state_contradictions(
                project_id, 3, "Марк приходит на склад", "m::x",
                {"global_state": "### Марк\nСОСТОЯНИЕ: мёртв\n"})
        assert isinstance(out, list)

    def test_bad_json_is_survived(self, project_id):
        from engine.prevalidation import _check_state_contradictions
        with patch("engine.prevalidation.call_model", return_value="не json"):
            out = _check_state_contradictions(project_id, 3, "задача", "m::x",
                                              {"global_state": "текст"})
        assert out == []

    def test_empty_state_skips_check(self, project_id):
        from engine.prevalidation import _check_state_contradictions
        with patch("engine.prevalidation.call_model", return_value='{"blocking": []}'):
            assert _check_state_contradictions(project_id, 1, "задача", "m::x", {}) == []

    def test_prevalidate_chapter_returns_shape(self, project_id):
        from engine.prevalidation import prevalidate_chapter
        answer = '{"ok": true, "blocking": [], "warnings": []}'
        with patch("engine.prevalidation.call_model", return_value=answer):
            out = prevalidate_chapter(project_id, 1, "написать главу", "m::x")
        assert isinstance(out, dict)
        for key in ("ok", "blocking", "warnings"):
            assert key in out
