#!/usr/bin/env python3
"""
Учёт расходов на вызовы моделей.

Движок не знал, во что обходится глава: ни токенов, ни стоимости никуда
не писалось. На вопрос «сколько потрачено» приходилось считать вызовы по
памяти и умножать на прикидку — а у перепродавца тариф вообще неизвестен.

Два правила, которые тесты стерегут:
  — учёт не должен ронять генерацию: текст главы автору важнее записи;
  — неизвестный тариф записывается как пустой, а не как ноль, иначе сумма
    выглядела бы полной, хотя часть трат в неё не вошла.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())


@pytest.fixture
def db(monkeypatch):
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "usage.db")
    dbc.init_db()
    return dbc


class TestPricing:
    def test_known_anthropic_model_is_priced(self):
        from engine.pricing import estimate_cost
        # 1 000 000 входных по $1 + 1 000 000 выходных по $5
        assert estimate_cost("anthropic_direct", "claude-haiku-4-5", 1_000_000, 1_000_000) == 6.0

    def test_dated_model_id_matches_its_price(self):
        """Идентификаторы приходят и с датой, и без — цена одна."""
        from engine.pricing import estimate_cost
        a = estimate_cost("anthropic_direct", "claude-haiku-4-5", 1000, 1000)
        b = estimate_cost("anthropic_direct", "claude-haiku-4-5-20251001", 1000, 1000)
        assert a == b

    def test_sonnet_is_twice_haiku(self):
        from engine.pricing import estimate_cost
        h = estimate_cost("anthropic_direct", "claude-haiku-4-5", 10_000, 2_000)
        s = estimate_cost("anthropic_direct", "claude-sonnet-5", 10_000, 2_000)
        assert s == pytest.approx(h * 2)

    def test_reseller_price_wins_over_our_table(self):
        """Провайдер знает свой тариф точнее — со скидками и кешированием."""
        from engine.pricing import estimate_cost
        got = estimate_cost("anthropic_direct", "claude-haiku-4-5", 1_000_000, 0,
                            reported_cost=0.25)
        assert got == 0.25

    def test_unknown_model_has_no_invented_price(self):
        from engine.pricing import estimate_cost
        assert estimate_cost("nano_gpt", "z-ai/glm-5.3", 5000, 4000) is None


class TestRecording:
    def test_usage_is_stored_and_summed(self, db):
        from engine.db_settings import record_api_usage, get_usage_totals
        record_api_usage("anthropic_direct", "claude-sonnet-5", 6000, 1300, 0.025, "critique")
        record_api_usage("anthropic_direct", "claude-sonnet-5", 6000, 1300, 0.025, "judge")
        t = get_usage_totals()
        assert t["calls"] == 2
        assert t["input_tokens"] == 12000
        assert t["cost_usd"] == pytest.approx(0.05)

    def test_unpriced_calls_are_counted_separately(self, db):
        """
        Иначе сумма выглядит полной, хотя часть трат в неё не вошла — то
        же семейство, что «оценка 0» вместо «оценки нет».
        """
        from engine.db_settings import record_api_usage, get_usage_totals
        record_api_usage("anthropic_direct", "claude-sonnet-5", 6000, 1300, 0.025)
        record_api_usage("nano_gpt", "z-ai/glm-5.3", 5000, 4000, None)
        t = get_usage_totals()
        assert t["calls"] == 2
        assert t["calls_unpriced"] == 1
        assert t["cost_usd"] == pytest.approx(0.025)

    def test_recording_failure_does_not_raise(self, db, monkeypatch):
        """Учёт побочен: отказ базы не должен ронять генерацию."""
        import engine.db_settings as dbs

        def boom(*a, **k):
            raise RuntimeError("база недоступна")

        monkeypatch.setattr(dbs, "get_conn", boom)
        dbs.record_api_usage("anthropic_direct", "claude-sonnet-5", 1, 1, 0.1)  # не падает


class TestDispatcherRecords:
    def _call(self, monkeypatch, db, usage_in, usage_out):
        import engine.api as api
        msg = MagicMock()
        msg.content = [MagicMock(text="текст главы")]
        msg.usage = MagicMock(input_tokens=usage_in, output_tokens=usage_out)
        monkeypatch.setattr(api, "_call_anthropic",
                            lambda *a, **k: (api._remember_usage(usage_in, usage_out),
                                             "текст главы")[1])
        return api.call_model("anthropic_direct::claude-sonnet-5", "sys", "usr",
                              anthropic_key="k", operation="critique")

    def test_call_is_recorded_with_its_cost(self, db, monkeypatch):
        from engine.db_settings import get_usage_totals
        assert self._call(monkeypatch, db, 6000, 1300) == "текст главы"
        t = get_usage_totals()
        assert t["calls"] == 1
        assert t["cost_usd"] == pytest.approx(6000 / 1e6 * 2 + 1300 / 1e6 * 10)

    def test_empty_usage_writes_no_row(self, db, monkeypatch):
        """Строка с нулями только засоряла бы сводку."""
        from engine.db_settings import get_usage_totals
        self._call(monkeypatch, db, 0, 0)
        assert get_usage_totals()["calls"] == 0


# ─── Оплаченный вызов учитывается, даже если упал разбор ─────────────────────
#
# Поймано 22.09 при переводе судьи на claude-sonnet-5. Пятнадцать вызовов
# подряд отработали и были оплачены, а разбор разбился о блок размышления
# (`'ThinkingBlock' object has no attribute 'text'`). Учёт показал
# «потрачено $0» при непустом счёте.
#
# Два дефекта в одном месте: разбор брал content[0] вместо первого
# ТЕКСТОВОГО блока, и запись расхода стояла после успеха вместо finally.

class TestBilledCallsAreRecorded:
    def _fail_after_response(self, monkeypatch, db):
        import engine.api as api

        def provider(*a, **k):
            api._remember_usage(6000, 1300)      # провайдер ответил — счётчик тикнул
            raise ValueError("разбор упал уже после ответа")

        monkeypatch.setattr(api, "_call_anthropic", provider)
        return api

    def test_usage_recorded_when_parsing_fails(self, db, monkeypatch):
        api = self._fail_after_response(monkeypatch, db)
        from engine.db_settings import get_usage_totals
        with pytest.raises(ValueError):
            api.call_model("anthropic_direct::claude-sonnet-5", "s", "u", anthropic_key="k")
        t = get_usage_totals()
        assert t["calls"] == 1, "оплаченный вызов не попал в учёт"
        assert t["cost_usd"] > 0

    def test_usage_recorded_when_answer_is_empty(self, db, monkeypatch):
        """Пустой ответ — тоже оплаченный вызов."""
        import engine.api as api
        from engine.db_settings import get_usage_totals

        def provider(*a, **k):
            api._remember_usage(6000, 5)
            return ""

        monkeypatch.setattr(api, "_call_anthropic", provider)
        with pytest.raises(ValueError, match="пустой ответ"):
            api.call_model("anthropic_direct::claude-sonnet-5", "s", "u", anthropic_key="k")
        assert get_usage_totals()["calls"] == 1


class TestThinkingBlocks:
    """Первым блоком у думающих моделей идёт размышление, а не текст."""

    def _blocks(self, *specs):
        out = []
        for kind, text in specs:
            b = MagicMock()
            b.type = kind
            if text is None:
                del b.text
            else:
                b.text = text
            out.append(b)
        return out

    def test_text_after_thinking_block_is_found(self):
        from engine.api import _first_text_block
        blocks = self._blocks(("thinking", None), ("text", "ответ критика"))
        assert _first_text_block(blocks) == "ответ критика"

    def test_empty_thinking_text_is_skipped(self):
        """У Sonnet 5 содержимое размышления по умолчанию пустая строка."""
        from engine.api import _first_text_block
        blocks = self._blocks(("thinking", ""), ("text", "ответ"))
        assert _first_text_block(blocks) == "ответ"

    def test_plain_text_response_still_works(self):
        from engine.api import _first_text_block
        assert _first_text_block(self._blocks(("text", "обычный ответ"))) == "обычный ответ"

    def test_no_text_block_raises_with_types_listed(self):
        from engine.api import _first_text_block
        with pytest.raises(ValueError, match="нет текстового блока"):
            _first_text_block(self._blocks(("thinking", None)))


def test_anthropic_caller_uses_the_first_text_block(monkeypatch):
    """
    Дыра, которую вскрыла фальсификация: тесты выше проверяют
    `_first_text_block`, но не то, что `_call_anthropic` её ЗОВЁТ. Возврат
    к `content[0].text` их не ронял — а именно он и был дефектом.
    """
    import engine.api as api

    thinking = MagicMock(); thinking.type = "thinking"; del thinking.text
    text = MagicMock(); text.type = "text"; text.text = "разбор главы"
    msg = MagicMock(content=[thinking, text],
                    usage=MagicMock(input_tokens=10, output_tokens=5),
                    stop_reason="end_turn")
    client = MagicMock()
    client.messages.create.return_value = msg
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **k: client)

    got = api._call_anthropic("claude-sonnet-5", "sys", "usr", "key", 100)
    assert got == "разбор главы", "вызов не использует первый текстовый блок"
