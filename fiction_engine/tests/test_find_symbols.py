#!/usr/bin/env python3
"""
Поиск символов в главе: два числа, которые нельзя менять поодиночке.

Текст обрезался до 3000 символов (26 % главы), ответ — до 800 токенов.
Замер 15.09 на главе в 11 345 символов, подсадка символа («нефритовый
секстант», вписан трижды с объяснением значения):

    обрезка 3000, лимит  800:   4 символа, подсадка в конце НЕ найдена
    полный текст, лимит  800:   ОТКАЗ — call_json бросает исключение
    полный текст, лимит 2500:  12 символов, подсадка найдена

Обрезка теряла символы из трёх четвертей главы. Но поднять её, не подняв
лимит ответа, значило бы заменить тихую потерю на громкий отказ: ответ
растёт вместе с входом, а веб-слой на исключении отдаёт пятисотку.

Отдельно: форма ответа не гарантирована — модель возвращает то объект с
«found», то сразу список.
"""

import sys
from unittest.mock import MagicMock, patch

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

MODEL = "anthropic_direct::test"


class TestWholeChapterIsSearched:
    def _capture(self, monkeypatch, reply):
        sent = {}
        import engine.pipeline_tasks as pt

        def fake(model, system, user, max_tokens=800):
            sent["user"], sent["max_tokens"] = user, max_tokens
            return reply

        monkeypatch.setattr(pt, "call_json", fake)
        return sent

    def test_symbol_at_the_end_reaches_the_model(self, monkeypatch):
        import engine.pipeline_tasks as pt
        sent = self._capture(monkeypatch, {"found": []})
        chapter = "Обычный текст главы. " * 400 + "\n\nНа полке стоял нефритовый секстант.\n"
        assert len(chapter) > 3000, "проверка потеряла смысл: глава короче прежней обрезки"
        pt.find_symbols_in_chapter(chapter, [], MODEL)
        assert "нефритовый секстант" in sent["user"], "конец главы не дошёл до поиска символов"

    def test_answer_budget_grew_with_the_text(self, monkeypatch):
        """
        Главное здесь. Полный текст при лимите 800 не терял данные, а
        отказывал целиком. Два числа связаны, и тест стережёт связь.
        """
        import engine.pipeline_tasks as pt
        from engine.pipeline_config import SYMBOLS_TEXT_LIMIT, SYMBOLS_MAX_TOKENS
        sent = self._capture(monkeypatch, {"found": []})
        pt.find_symbols_in_chapter("текст " * 2000, [], MODEL)
        assert sent["max_tokens"] == SYMBOLS_MAX_TOKENS
        assert SYMBOLS_MAX_TOKENS >= 2000, (
            "лимит ответа опущен: на главе целиком его не хватит, "
            "call_json бросит исключение и пользователь получит 500")
        assert SYMBOLS_TEXT_LIMIT >= 10000

    def test_pathological_length_is_capped(self, monkeypatch):
        import engine.pipeline_tasks as pt
        from engine.pipeline_config import SYMBOLS_TEXT_LIMIT
        sent = self._capture(monkeypatch, {"found": []})
        pt.find_symbols_in_chapter("А" * (SYMBOLS_TEXT_LIMIT * 3), [], MODEL)
        assert len(sent["user"]) < SYMBOLS_TEXT_LIMIT * 2


class TestResponseShapeIsNormalised:
    """Веб-слой делает `{"ok": True, **result}` — на списке это TypeError и 500."""

    def _run(self, monkeypatch, reply):
        import engine.pipeline_tasks as pt
        monkeypatch.setattr(pt, "call_json", lambda *a, **k: reply)
        return pt.find_symbols_in_chapter("текст главы " * 100, [], MODEL)

    def test_object_passes_through(self, monkeypatch):
        got = self._run(monkeypatch, {"found": [{"name": "секстант"}], "note": "ок"})
        assert got["found"][0]["name"] == "секстант"
        assert got["note"] == "ок"

    def test_bare_list_becomes_an_object(self, monkeypatch):
        got = self._run(monkeypatch, [{"name": "секстант"}])
        assert isinstance(got, dict), "список дойдёт до `**result` и уронит веб-слой"
        assert got["found"][0]["name"] == "секстант"

    def test_unexpected_shape_does_not_crash(self, monkeypatch):
        got = self._run(monkeypatch, "просто строка")
        assert isinstance(got, dict) and got["found"] == []

    def test_object_without_found_gets_it(self, monkeypatch):
        got = self._run(monkeypatch, {"note": "ничего не нашёл"})
        assert got["found"] == []

    def test_result_is_always_unpackable(self, monkeypatch):
        """Ровно то, что делает веб-слой."""
        for reply in ({"found": []}, [{"name": "х"}], None, "строка", 42):
            got = self._run(monkeypatch, reply)
            assert dict(ok=True, **got)
