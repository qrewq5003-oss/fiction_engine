"""Миграции схемы планировщика."""

import pytest


class TestMigrations:
    def test_version_recorded(self):
        from engine.migrations import get_current_version, MIGRATIONS
        assert get_current_version() == max(MIGRATIONS)

    def test_idempotent(self):
        """Повторный прогон ничего не меняет и не падает."""
        from engine.migrations import apply_migrations, get_current_version
        before = get_current_version()
        apply_migrations()
        apply_migrations()
        assert get_current_version() == before

    def test_all_migrations_have_commands(self):
        from engine.migrations import MIGRATIONS
        for version, cmds in MIGRATIONS.items():
            assert isinstance(version, int)
            assert cmds, f"миграция {version} пуста"

    def test_versions_are_sequential(self):
        """Пропуск номера означал бы, что миграцию потеряли при слиянии."""
        from engine.migrations import MIGRATIONS
        nums = sorted(MIGRATIONS)
        assert nums == list(range(1, len(nums) + 1)), nums

    def test_schema_has_expected_tables(self):
        from engine.db import get_conn
        with get_conn() as conn:
            tables = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("projects", "acts", "scenes", "scene_links", "scene_snapshots"):
            assert t in tables, f"нет таблицы {t}"

    def test_foreign_keys_enabled(self):
        from engine.db import get_conn
        with get_conn() as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
