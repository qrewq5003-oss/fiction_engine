"""test_engine_loaders_misc.py — engine_available, get_token_budget"""
import pytest
from unittest.mock import patch


class TestEngineAvailable:
    def test_returns_bool(self):
        from engine.engine_loaders import engine_available
        assert isinstance(engine_available(), bool)

    def test_false_when_dir_missing(self, tmp_path):
        from engine.engine_loaders import engine_available
        with patch("engine.engine_loaders.get_engine_path",
                   return_value=tmp_path / "NONEXISTENT"):
            assert engine_available() is False

    def test_true_when_dir_exists(self, tmp_path):
        from engine.engine_loaders import engine_available
        fake = tmp_path / "UNIFIED_ENGINE_MASTER"
        fake.mkdir()
        with patch("engine.engine_loaders.get_engine_path", return_value=fake):
            assert engine_available() is True


class TestGetTokenBudget:
    def test_claude_positive_int(self):
        from engine.engine_loaders import get_token_budget
        r = get_token_budget("anthropic::claude-3-5-sonnet")
        assert isinstance(r, int) and r > 0

    def test_gemini_positive_int(self):
        from engine.engine_loaders import get_token_budget
        assert get_token_budget("gemini::gemini-1.5-pro") > 0

    def test_gpt4o_positive_int(self):
        from engine.engine_loaders import get_token_budget
        assert get_token_budget("openai::gpt-4o") > 0

    def test_deepseek_positive_int(self):
        from engine.engine_loaders import get_token_budget
        assert get_token_budget("deepseek::deepseek-chat") > 0

    def test_empty_returns_default(self):
        from engine.engine_loaders import get_token_budget
        r = get_token_budget("")
        assert isinstance(r, int) and r > 0

    def test_unknown_returns_default(self):
        from engine.engine_loaders import get_token_budget
        r = get_token_budget("unknown::something-v9")
        assert isinstance(r, int) and r > 0


class TestGetModuleDependencies:
    def test_returns_dict(self):
        from engine.engine_loaders import get_module_dependencies
        with patch("engine.engine_loaders.load_module_dependencies_from_index",
                   return_value=None):
            result = get_module_dependencies()
        assert isinstance(result, dict)

    def test_uses_index_when_available(self):
        from engine.engine_loaders import get_module_dependencies
        fake = {"genre": ["base", "arc"]}
        with patch("engine.engine_loaders.load_module_dependencies_from_index",
                   return_value=fake):
            result = get_module_dependencies()
        assert result == fake

    def test_falls_back_to_hardcode_when_no_index(self):
        from engine.engine_loaders import get_module_dependencies
        with patch("engine.engine_loaders.load_module_dependencies_from_index",
                   return_value=None):
            result = get_module_dependencies()
        assert len(result) > 0
