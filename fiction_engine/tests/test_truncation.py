

# ─── Обрыв на полуслове ───────────────────────────────────────────────────────
#
# Глава нужной длины, провайдер сообщил чистый stop, а текст кончается
# посреди фразы — этого не ловил НИКТО.
#
# Судья к такому слеп. Проверка 14.09 на пяти главах: срез в одной и той
# же точке (75% текста), разная только граница —
#
#     оригинал              структура 6.4
#     обрыв на полуслове    структура 6.4  (+0.0)
#     обрыв в предложении   структура 6.2  (-0.2)
#     обрыв на точке        структура 6.6  (+0.2)
#
# при разбросе 0.8. Один текст, оборванный посреди слова, даже вырос с 6
# до 8. Спрошенный про финал прямо, судья тоже не реагировал (+0.2).
#
# Вывод: завершённость — свойство арифметическое, и проверять его надо
# арифметикой, а не спрашивать у языковой модели.

class TestMidSentenceCut:
    LONG = "Он шёл по улице и думал о случившемся. " * 400   # 3200 слов

    def _check(self, text, monkeypatch, stop="stop"):
        import engine.api as api
        monkeypatch.setattr(api, "get_last_stop_reason", lambda: stop)
        from engine.pipeline_tasks import detect_truncation
        return detect_truncation(text, len(text.split()))

    def test_chapter_cut_mid_word_is_caught(self, monkeypatch):
        res = self._check(self.LONG + "Потом он повернул к реке и", monkeypatch)
        assert res["truncated"] is True
        assert res["reason"] == "mid_sentence"

    def test_chapter_cut_after_comma_is_caught(self, monkeypatch):
        res = self._check(self.LONG + "Он молчал, слушая дыхание друга,", monkeypatch)
        assert res["reason"] == "mid_sentence"

    def test_complete_chapter_passes(self, monkeypatch):
        assert self._check(self.LONG, monkeypatch)["truncated"] is False

    # ── Ложных срабатываний быть не должно ──

    def test_ending_with_quote_passes(self, monkeypatch):
        res = self._check(self.LONG + '«Я приду завтра».', monkeypatch)
        assert res["truncated"] is False

    def test_ending_with_ellipsis_passes(self, monkeypatch):
        assert self._check(self.LONG + "И всё же…", monkeypatch)["truncated"] is False

    def test_ending_with_markdown_emphasis_passes(self, monkeypatch):
        res = self._check(self.LONG + "*Он никогда не вернулся.*", monkeypatch)
        assert res["truncated"] is False

    def test_ending_with_question_passes(self, monkeypatch):
        assert self._check(self.LONG + "Кто это был?", monkeypatch)["truncated"] is False

    def test_trailing_whitespace_is_ignored(self, monkeypatch):
        res = self._check(self.LONG + "Конец главы.\n\n  \n", monkeypatch)
        assert res["truncated"] is False

    # ── Не перехватывает более важные причины ──

    def test_max_tokens_still_reported_first(self, monkeypatch):
        """Жёсткий обрыв провайдера — точнее и должен называться первым."""
        res = self._check(self.LONG + "и тогда он", monkeypatch, stop="length")
        assert res["reason"] == "max_tokens"

    def test_short_chapter_still_reported(self, monkeypatch):
        res = self._check("Короткая глава. " * 50, monkeypatch)
        assert res["reason"] == "short"
