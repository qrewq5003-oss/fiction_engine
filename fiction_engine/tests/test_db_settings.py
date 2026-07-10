"""
test_db_settings.py — тесты db_settings.py

Покрываем: API ключи, настройки, активный проект, prep layer.
"""

import os
import pytest
from unittest.mock import patch


class TestApiKeys:
    def test_save_and_get_api_key(self, use_temp_db):
        from engine.db_settings import save_api_key, get_api_key
        save_api_key("anthropic_direct", "sk-ant-test123")
        assert get_api_key("anthropic_direct") == "sk-ant-test123"

    def test_get_api_key_falls_back_to_env(self, use_temp_db):
        from engine.db_settings import get_api_key
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key-123"}):
            result = get_api_key("anthropic_direct")
        assert result == "env-key-123"

    def test_get_api_key_db_takes_priority_over_env(self, use_temp_db):
        from engine.db_settings import save_api_key, get_api_key
        save_api_key("anthropic_direct", "db-key-456")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key-123"}):
            result = get_api_key("anthropic_direct")
        assert result == "db-key-456"

    def test_get_api_key_nonexistent_returns_none(self, use_temp_db):
        from engine.db_settings import get_api_key
        assert get_api_key("nonexistent_provider") is None

    def test_get_all_api_keys_masks_values(self, use_temp_db):
        from engine.db_settings import save_api_key, get_all_api_keys
        save_api_key("anthropic_direct", "sk-ant-verylongkey1234")
        keys = get_all_api_keys()
        assert "anthropic_direct" in keys
        # Значение маскировано
        assert "verylongkey1234" not in keys["anthropic_direct"]
        assert "..." in keys["anthropic_direct"]

    def test_get_all_api_keys_empty(self, use_temp_db):
        from engine.db_settings import get_all_api_keys
        assert get_all_api_keys() == {}

    def test_save_api_key_overwrite(self, use_temp_db):
        from engine.db_settings import save_api_key, get_api_key
        save_api_key("anthropic_direct", "ключ-первый")
        save_api_key("anthropic_direct", "ключ-второй")
        assert get_api_key("anthropic_direct") == "ключ-второй"


class TestSettings:
    def test_set_and_get_setting(self, use_temp_db):
        from engine.db_settings import set_setting, get_setting
        set_setting("my_key", "my_value")
        assert get_setting("my_key") == "my_value"

    def test_get_nonexistent_setting_returns_none(self, use_temp_db):
        from engine.db_settings import get_setting
        assert get_setting("нет_такого") is None

    def test_set_setting_overwrite(self, use_temp_db):
        from engine.db_settings import set_setting, get_setting
        set_setting("k", "v1")
        set_setting("k", "v2")
        assert get_setting("k") == "v2"


class TestActiveProject:
    def test_set_and_get_active_project(self, use_temp_db):
        from engine.db_settings import set_active_project, get_active_project_id
        set_active_project(42)
        assert get_active_project_id() == 42

    def test_get_active_project_initially_none(self, use_temp_db):
        from engine.db_settings import get_active_project_id
        assert get_active_project_id() is None

    def test_switch_active_project(self, use_temp_db):
        from engine.db_settings import set_active_project, get_active_project_id
        set_active_project(1)
        set_active_project(2)
        assert get_active_project_id() == 2


class TestPrepLayer:
    def test_get_prep_returns_defaults_for_new_project(self, project_id):
        from engine.db_settings import get_prep, PREP_SECTIONS, PREP_DEFAULTS
        prep = get_prep(project_id)
        assert set(prep.keys()) == set(PREP_SECTIONS.keys())
        # Новый проект — получаем дефолты
        for section in PREP_SECTIONS:
            assert prep[section] == PREP_DEFAULTS[section]

    def test_save_and_get_prep(self, project_id):
        from engine.db_settings import save_prep, get_prep
        save_prep(project_id, "characters", "## Герой\nИмя: Иван")
        prep = get_prep(project_id)
        assert prep["characters"] == "## Герой\nИмя: Иван"

    def test_save_prep_upsert(self, project_id):
        from engine.db_settings import save_prep, get_prep
        save_prep(project_id, "notes", "заметка 1")
        save_prep(project_id, "notes", "заметка 2")
        prep = get_prep(project_id)
        assert prep["notes"] == "заметка 2"

    def test_get_prep_context_empty_for_new_project(self, project_id):
        from engine.db_settings import get_prep_context
        # У нового проекта prep = дефолты, контекст пустой
        ctx = get_prep_context(project_id)
        assert ctx == ""

    def test_get_prep_context_nonempty_after_save(self, project_id):
        from engine.db_settings import save_prep, get_prep_context
        save_prep(project_id, "characters", "## Герой\nИмя: Иван Петров")
        ctx = get_prep_context(project_id)
        assert "Иван Петров" in ctx

    def test_prep_sections_all_present(self, use_temp_db):
        from engine.db_settings import PREP_SECTIONS
        expected = {"characters", "world", "plot", "notes"}
        assert set(PREP_SECTIONS.keys()) == expected
