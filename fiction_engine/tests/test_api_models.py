"""test_api_models.py — get_all_models_flat, parse_model_value"""
import pytest


class TestGetAllModelsFlat:
    def test_returns_nonempty_list(self):
        from engine.api import get_all_models_flat
        result = get_all_models_flat()
        assert isinstance(result, list) and len(result) > 0

    def test_each_item_has_value_and_label(self):
        from engine.api import get_all_models_flat
        for m in get_all_models_flat():
            assert "value" in m and "label" in m

    def test_value_format_is_provider_model(self):
        from engine.api import get_all_models_flat
        for m in get_all_models_flat():
            assert "::" in m["value"], f"bad format: {m['value']}"

    def test_no_duplicate_values(self):
        from engine.api import get_all_models_flat
        values = [m["value"] for m in get_all_models_flat()]
        assert len(values) == len(set(values))


class TestParseModelValue:
    def test_valid_splits_correctly(self):
        from engine.api import parse_model_value
        p, m = parse_model_value("anthropic::claude-3-5-sonnet")
        assert p == "anthropic" and m == "claude-3-5-sonnet"

    def test_nano_format(self):
        from engine.api import parse_model_value
        p, m = parse_model_value("nano_gpt::gpt-4o-mini")
        assert p == "nano_gpt" and m == "gpt-4o-mini"

    def test_missing_separator_raises(self):
        from engine.api import parse_model_value
        with pytest.raises(ValueError, match="Неверный формат"):
            parse_model_value("no_separator_here")

    def test_empty_raises(self):
        from engine.api import parse_model_value
        with pytest.raises((ValueError, Exception)):
            parse_model_value("")
