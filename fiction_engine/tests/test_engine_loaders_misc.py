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
    def test_single_source_is_config(self):
        from engine.engine_config import MODULE_DEPENDENCIES
        from engine.engine_loaders import get_module_dependencies
        assert get_module_dependencies() is MODULE_DEPENDENCIES

    def test_index_has_no_copy(self):
        """Вторая копия графа в INDEX.json расходилась бы с кодом молча."""
        import json
        from pathlib import Path
        index = Path(__file__).resolve().parents[2] / "UNIFIED_ENGINE_MASTER" / "INDEX.json"
        assert "module_dependencies" not in json.loads(index.read_text(encoding="utf-8"))

