"""
test_scene_editor.py — engine/scene_editor.py

Покрываем:
  A. Константы и структура
     1. EDIT_MODES содержит ожидаемые ключи
     2. MODE_PROMPTS покрывает все ключи из EDIT_MODES
     3. Каждый MODE_PROMPT непустой

  B. edit_scene — редактирование текста
     4. Неизвестный mode без custom_instruction → ValueError
     5. custom_instruction игнорирует mode → вызывает LLM с custom_instruction
     6. Известный mode → вызывает LLM с соответствующей инструкцией
     7. Активный голосовой профиль → попадает в промпт
     8. Нет активного голоса → голосовой блок пустой (нет краша)
     9. LLM бросает исключение → пробрасывается (нет скрытого try/except)
    10. Результат — строка (возвращает то что вернул LLM)

  C. analyze_voice — анализ голоса
    11. Вызывает LLM → возвращает строку
    12. Промпт содержит переданный текст
    13. Пустой текст → не падает, вызывает LLM
"""

import pytest
from unittest.mock import patch, MagicMock, call


class TestConstants:
    """A. Константы и структура."""

    def test_edit_modes_has_expected_keys(self):
        from engine.scene_editor import EDIT_MODES
        expected = {"tempo", "dialogue", "emotions", "voice", "subtext",
                    "cliches", "opening", "closing", "sensory", "grammar"}
        assert set(EDIT_MODES.keys()) == expected

    def test_mode_prompts_covers_all_edit_modes(self):
        from engine.scene_editor import EDIT_MODES, MODE_PROMPTS
        for key in EDIT_MODES:
            assert key in MODE_PROMPTS, f"MODE_PROMPTS missing key: '{key}'"

    def test_all_prompts_nonempty(self):
        from engine.scene_editor import MODE_PROMPTS
        for key, prompt in MODE_PROMPTS.items():
            assert prompt and len(prompt.strip()) > 10, f"Prompt '{key}' is too short"


class TestEditScene:
    """B. edit_scene."""

    def _mock_keys(self):
        return {k: "test-key" for k in ("anthropic", "nano", "openai", "gemini", "deepseek")}

    def test_unknown_mode_no_custom_raises(self, project_id):
        from engine.scene_editor import edit_scene
        with patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()), \
             patch("engine.scene_editor.get_active_voice", return_value=None):
            with pytest.raises(ValueError, match="Неизвестный режим"):
                edit_scene(project_id, "текст", "nonexistent_mode_xyz", "model:v1")

    def test_custom_instruction_overrides_mode(self, project_id):
        from engine.scene_editor import edit_scene
        captured = {}

        def fake_call_model(model, sys_p, user_p, **kwargs):
            captured["user"] = user_p
            return "результат"

        with patch("engine.scene_editor.call_model", side_effect=fake_call_model), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()), \
             patch("engine.scene_editor.get_active_voice", return_value=None):
            result = edit_scene(project_id, "текст", "tempo", "model:v1",
                                custom_instruction="Переписать в нуар-стиле")

        assert "Переписать в нуар-стиле" in captured["user"]
        assert result == "результат"

    def test_known_mode_uses_mode_prompt(self, project_id):
        from engine.scene_editor import edit_scene, MODE_PROMPTS
        captured = {}

        def fake_call_model(model, sys_p, user_p, **kwargs):
            captured["user"] = user_p
            return "редактированный текст"

        with patch("engine.scene_editor.call_model", side_effect=fake_call_model), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()), \
             patch("engine.scene_editor.get_active_voice", return_value=None):
            edit_scene(project_id, "входной текст", "dialogue", "model:v1")

        # Часть инструкции из MODE_PROMPTS["dialogue"] должна быть в промпте
        assert "диалог" in captured["user"].lower() or "ЗАДАЧА" in captured["user"]

    def test_active_voice_included_in_prompt(self, project_id):
        from engine.scene_editor import edit_scene
        captured = {}
        mock_voice = {"name": "Тест", "profile": "УНИКАЛЬНЫЙ_ПРОФИЛЬ_ГОЛОСА_ТЕСТ"}

        def fake_call_model(model, sys_p, user_p, **kwargs):
            captured["user"] = user_p
            return "результат"

        with patch("engine.scene_editor.call_model", side_effect=fake_call_model), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()), \
             patch("engine.scene_editor.get_active_voice", return_value=mock_voice):
            edit_scene(project_id, "текст", "tempo", "model:v1")

        assert "УНИКАЛЬНЫЙ_ПРОФИЛЬ_ГОЛОСА_ТЕСТ" in captured["user"]

    def test_no_active_voice_no_crash(self, project_id):
        from engine.scene_editor import edit_scene

        with patch("engine.scene_editor.call_model", return_value="результат"), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()), \
             patch("engine.scene_editor.get_active_voice", return_value=None):
            result = edit_scene(project_id, "текст", "tempo", "model:v1")

        assert result == "результат"

    def test_llm_exception_propagates(self, project_id):
        """edit_scene не скрывает исключения LLM — они пробрасываются наверх."""
        from engine.scene_editor import edit_scene

        def crashing_model(*a, **kw):
            raise ConnectionError("API недоступен")

        with patch("engine.scene_editor.call_model", side_effect=crashing_model), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()), \
             patch("engine.scene_editor.get_active_voice", return_value=None):
            with pytest.raises(ConnectionError):
                edit_scene(project_id, "текст", "tempo", "model:v1")

    def test_returns_llm_result_as_string(self, project_id):
        from engine.scene_editor import edit_scene

        with patch("engine.scene_editor.call_model", return_value="ФИНАЛЬНЫЙ_ТЕКСТ"), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()), \
             patch("engine.scene_editor.get_active_voice", return_value=None):
            result = edit_scene(project_id, "текст", "grammar", "model:v1")

        assert result == "ФИНАЛЬНЫЙ_ТЕКСТ"

    @pytest.mark.parametrize("mode", ["tempo", "dialogue", "emotions", "voice",
                                       "subtext", "cliches", "opening", "closing",
                                       "sensory", "grammar"])
    def test_all_modes_work(self, project_id, mode):
        """Каждый из 10 режимов проходит без ошибок."""
        from engine.scene_editor import edit_scene
        with patch("engine.scene_editor.call_model", return_value="ok"), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()), \
             patch("engine.scene_editor.get_active_voice", return_value=None):
            result = edit_scene(project_id, "тестовый текст", mode, "model:v1")
        assert result == "ok"

    def test_text_included_in_prompt(self, project_id):
        from engine.scene_editor import edit_scene
        captured = {}

        def fake_call_model(model, sys_p, user_p, **kwargs):
            captured["user"] = user_p
            return "результат"

        with patch("engine.scene_editor.call_model", side_effect=fake_call_model), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()), \
             patch("engine.scene_editor.get_active_voice", return_value=None):
            edit_scene(project_id, "УНИКАЛЬНЫЙ_ВХОДНОЙ_ТЕКСТ_123", "tempo", "model:v1")

        assert "УНИКАЛЬНЫЙ_ВХОДНОЙ_ТЕКСТ_123" in captured["user"]


class TestAnalyzeVoice:
    """C. analyze_voice."""

    def _mock_keys(self):
        return {k: "test-key" for k in ("anthropic", "nano", "openai", "gemini", "deepseek")}

    def test_returns_string(self):
        from engine.scene_editor import analyze_voice
        with patch("engine.scene_editor.call_model", return_value="Анализ голоса"), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()):
            result = analyze_voice("Текст для анализа.", "model:v1")
        assert isinstance(result, str)
        assert result == "Анализ голоса"

    def test_text_in_prompt(self):
        from engine.scene_editor import analyze_voice
        captured = {}

        def fake_call(model, sys_p, user_p, **kwargs):
            captured["user"] = user_p
            return "анализ"

        with patch("engine.scene_editor.call_model", side_effect=fake_call), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()):
            analyze_voice("УНИКАЛЬНЫЙ_ТЕКСТ_АНАЛИЗА", "model:v1")

        assert "УНИКАЛЬНЫЙ_ТЕКСТ_АНАЛИЗА" in captured["user"]

    def test_empty_text_no_crash(self):
        from engine.scene_editor import analyze_voice
        with patch("engine.scene_editor.call_model", return_value="пусто"), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()):
            result = analyze_voice("", "model:v1")
        assert isinstance(result, str)

    def test_prompt_contains_analysis_structure(self):
        """Промпт содержит структуру анализа (ТЕМП, ДИАЛОГ и т.д.)."""
        from engine.scene_editor import analyze_voice
        captured = {}

        def fake_call(model, sys_p, user_p, **kwargs):
            captured["user"] = user_p
            return "анализ"

        with patch("engine.scene_editor.call_model", side_effect=fake_call), \
             patch("engine.scene_editor.get_api_keys_dict", return_value=self._mock_keys()):
            analyze_voice("Какой-то текст.", "model:v1")

        assert "ТЕМП" in captured["user"]
        assert "ДИАЛОГ" in captured["user"].upper() or "АТРИБУЦ" in captured["user"].upper()
