"""test_pipeline_parse.py — parse_score, parse_verdict (pure functions)"""
import pytest


class TestParseScore:
    def test_itog_parsed(self):
        from engine.pipeline import parse_score
        assert parse_score("ГОЛОС: 8\nИТОГ: 38\nВЕРДИКТ: ПРИНЯТЬ") == pytest.approx(38.0)

    def test_fractional(self):
        from engine.pipeline import parse_score
        assert parse_score("ИТОГ: 38.5") == pytest.approx(38.5)

    def test_fallback_to_sum(self):
        from engine.pipeline import parse_score
        text = "ГОЛОС: 7\nСТРУКТУРА: 8\nПЕРСОНАЖИ: 7\nСЦЕНЫ: 8\nДИАЛОГ: 7"
        assert parse_score(text) == pytest.approx(37.0)

    def test_itog_wins_over_sum(self):
        from engine.pipeline import parse_score
        text = "ГОЛОС: 1\nСТРУКТУРА: 1\nПЕРСОНАЖИ: 1\nСЦЕНЫ: 1\nДИАЛОГ: 1\nИТОГ: 40"
        assert parse_score(text) == pytest.approx(40.0)

    def test_empty_returns_zero(self):
        from engine.pipeline import parse_score
        assert parse_score("") == pytest.approx(0.0)

    def test_no_markers_returns_zero(self):
        from engine.pipeline import parse_score
        assert parse_score("случайный текст без оценок") == pytest.approx(0.0)

    def test_case_insensitive(self):
        from engine.pipeline import parse_score
        assert parse_score("итог: 35") == pytest.approx(35.0)


class TestParseVerdict:
    def test_prinyat(self):
        from engine.pipeline import parse_verdict
        assert parse_verdict("ВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: хорошо") == "ПРИНЯТЬ"

    def test_na_dorabotku(self):
        from engine.pipeline import parse_verdict
        assert parse_verdict("ИТОГ: 30\nВЕРДИКТ: НА ДОРАБОТКУ") == "НА ДОРАБОТКУ"

    def test_empty_defaults_to_na_dorabotku(self):
        from engine.pipeline import parse_verdict
        assert parse_verdict("") == "НА ДОРАБОТКУ"

    def test_no_verdict_defaults(self):
        from engine.pipeline import parse_verdict
        assert parse_verdict("текст без вердикта") == "НА ДОРАБОТКУ"

    def test_case_insensitive(self):
        from engine.pipeline import parse_verdict
        assert parse_verdict("вердикт: принять") == "ПРИНЯТЬ"

    def test_result_always_uppercase(self):
        from engine.pipeline import parse_verdict
        result = parse_verdict("ВЕРДИКТ: ПРИНЯТЬ")
        assert result == result.upper()
