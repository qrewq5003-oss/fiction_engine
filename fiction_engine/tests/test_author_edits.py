"""
test_author_edits.py — db_chapters.py::save_author_edit, get_author_edit_patterns

DATA_DRIVEN_LEARNING: сохранение и чтение паттернов правок автора.
Эти функции вызываются при каждом accept/reject в pipeline.
"""
import pytest


def _make_run(project_id):
    from engine.db_narrative import create_pipeline_run
    return create_pipeline_run(project_id, 1, "m", "m", "m", "m")


ORIG  = "Оригинальный текст главы. " * 20
ACCPT = "Принятый текст главы. " * 20


# ─── save_author_edit ─────────────────────────────────────────────────────────

class TestSaveAuthorEdit:
    def test_returns_true_on_success(self, project_id):
        from engine.db_chapters import save_author_edit
        run_id = _make_run(project_id)
        result = save_author_edit(project_id, 1, run_id, ORIG, ACCPT)
        assert result is True

    def test_saves_accept_action(self, project_id):
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, ACCPT, action="accept")
        patterns = get_author_edit_patterns(project_id)
        assert "accept" in patterns

    def test_saves_reject_action(self, project_id):
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, "",
                         action="reject", rejection_reason="Темп плохой")
        patterns = get_author_edit_patterns(project_id)
        assert "reject" in patterns

    def test_saves_manual_edit_action(self, project_id):
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, ACCPT + " (правка)",
                         action="manual_edit")
        patterns = get_author_edit_patterns(project_id)
        assert "manual_edit" in patterns

    def test_saves_judge_score(self, project_id):
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, ACCPT,
                         action="accept", judge_score=38.5)
        patterns = get_author_edit_patterns(project_id)
        assert "38.5" in patterns

    def test_saves_rejection_reason(self, project_id):
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, "",
                         action="reject", rejection_reason="Диалог неживой")
        patterns = get_author_edit_patterns(project_id)
        assert "Диалог неживой" in patterns

    def test_saves_without_judge_score(self, project_id):
        """judge_score может быть None — это нормально."""
        from engine.db_chapters import save_author_edit
        run_id = _make_run(project_id)
        result = save_author_edit(project_id, 1, run_id, ORIG, ACCPT,
                                  judge_score=None)
        assert result is True

    def test_multiple_edits_same_project(self, project_id):
        """Несколько записей для одного проекта — все сохраняются."""
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        for ch in range(1, 4):
            save_author_edit(project_id, ch, run_id, ORIG, ACCPT,
                             action="accept", judge_score=float(ch * 10))
        patterns = get_author_edit_patterns(project_id)
        assert "10.0" in patterns
        assert "20.0" in patterns
        assert "30.0" in patterns

    def test_chapter_num_in_output(self, project_id):
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 7, run_id, ORIG, ACCPT, action="accept")
        patterns = get_author_edit_patterns(project_id)
        assert "7" in patterns

    def test_returns_false_on_db_error(self, project_id):
        """error_boundary → возвращает False (fallback) при ошибке БД."""
        from engine.db_chapters import save_author_edit
        from unittest.mock import patch
        with patch("engine.db_chapters.get_conn", side_effect=Exception("DB down")):
            result = save_author_edit(project_id, 1, 0, ORIG, ACCPT)
        assert result is False


# ─── get_author_edit_patterns ─────────────────────────────────────────────────

class TestGetAuthorEditPatterns:
    def test_empty_string_when_no_edits(self, project_id):
        from engine.db_chapters import get_author_edit_patterns
        assert get_author_edit_patterns(project_id) == ""

    def test_returns_string(self, project_id):
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, ACCPT, action="accept")
        result = get_author_edit_patterns(project_id)
        assert isinstance(result, str)

    def test_each_edit_on_own_line(self, project_id):
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, ACCPT, action="accept")
        save_author_edit(project_id, 2, run_id, ORIG, "", action="reject")
        lines = get_author_edit_patterns(project_id).strip().split("\n")
        assert len(lines) == 2

    def test_n_limit_respected(self, project_id):
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        for ch in range(1, 12):
            save_author_edit(project_id, ch, run_id, ORIG, ACCPT, action="accept")
        lines = get_author_edit_patterns(project_id, n=5).strip().split("\n")
        assert len(lines) <= 5

    def test_most_recent_first(self, project_id):
        """ORDER BY created_at DESC — последние правки первые."""
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, ACCPT,
                         action="accept", judge_score=30.0)
        save_author_edit(project_id, 2, run_id, ORIG, ACCPT,
                         action="reject", judge_score=40.0)
        patterns = get_author_edit_patterns(project_id)
        lines = patterns.strip().split("\n")
        # Последняя запись (гл.2, reject) должна быть первой строкой
        assert "reject" in lines[0]

    def test_format_contains_chapter_action_score(self, project_id):
        """Формат: Гл.N [action] score=X — reason"""
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 3, run_id, ORIG, ACCPT,
                         action="manual_edit", judge_score=35.0,
                         rejection_reason="")
        result = get_author_edit_patterns(project_id)
        assert "Гл.3" in result
        assert "manual_edit" in result
        assert "35.0" in result

    def test_empty_reason_shows_dash(self, project_id):
        """Если rejection_reason пустая — выводится '—'."""
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, ACCPT,
                         action="accept", rejection_reason="")
        result = get_author_edit_patterns(project_id)
        assert "—" in result

    def test_isolation_between_projects(self, project_id):
        """Правки одного проекта не видны в другом."""
        from engine.db_chapters import save_author_edit, get_author_edit_patterns
        from engine.db_projects import create_project
        project2 = create_project("Второй проект", "детектив")
        run_id = _make_run(project_id)
        save_author_edit(project_id, 1, run_id, ORIG, ACCPT, action="accept")
        assert get_author_edit_patterns(project2) == ""

    def test_returns_empty_string_on_db_error(self, project_id):
        """error_boundary → возвращает '' (fallback) при ошибке."""
        from engine.db_chapters import get_author_edit_patterns
        from unittest.mock import patch
        with patch("engine.db_chapters.get_conn", side_effect=Exception("DB down")):
            result = get_author_edit_patterns(project_id)
        assert result == ""
