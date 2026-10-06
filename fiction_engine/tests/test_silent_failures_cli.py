"""
Находки F5 и F7 первого аудита (AUDIT_UNIFIED.md).

F5: после сохранения главы отказ генерации L3 и авто-оценки гасился без
записи в лог — L3 молча не создавалась, и следующие главы теряли память.
F7: CLI делал int() от ввода и падал на опечатке в номере главы.
"""
from unittest.mock import patch


def test_l3_failure_is_logged(project_id):
    from web.blueprints import helpers
    with patch("engine.pipeline.generate_l3", side_effect=RuntimeError("сеть")), \
         patch.object(helpers, "log_web_error") as log, \
         patch("engine.pipeline.auto_drift_check_if_needed", return_value=None), \
         patch("engine.pipeline.generate_director_note_for_chapter", return_value=None), \
         patch.object(helpers, "_get_scorer_model", return_value=None):
        res = helpers.after_chapter_saved(project_id, 1, "Текст главы. " * 50, "m::x")
    assert res["l3_generated"] is False
    assert any("L3" in c.args[0] for c in log.call_args_list)


def test_auto_score_failure_is_logged(project_id):
    from web.blueprints import helpers
    with patch("engine.db.get_api_key", return_value="k"), \
         patch("engine.pipeline.score_text", side_effect=RuntimeError("сеть")), \
         patch.object(helpers, "log_web_error") as log:
        assert helpers._auto_score_chapter(project_id, 1, "Текст.", "nano_gpt::x") is None
    assert any("авто-оценка" in c.args[0] for c in log.call_args_list)


def test_prompt_int_asks_again_on_typo(capsys):
    import cli
    with patch("builtins.input", side_effect=["пять", "5"]):
        assert cli.prompt_int("Номер главы", 3) == 5
    assert "Нужно число" in capsys.readouterr().out


def test_prompt_int_empty_gives_default():
    import cli
    with patch("builtins.input", side_effect=[""]):
        assert cli.prompt_int("Номер главы", 3) == 3
