"""Анализ главы с кавычками внутри строки: State обновляется, а битый JSON не «применяется» молча (дымовая книга 19.10)."""
import json
from unittest.mock import MagicMock

BROKEN = ('{"global_state_changes": [{"name": "Ника", "состояние": "напряжена", "локация": "вахта"}], '
          '"details": ["Серый журнал учёта «Театр "Подвал"», вырвана страница за пятницу"], '
          '"next_context": "Ника идёт к Артёму"}')


def test_stray_quotes_repaired():
    from engine.pipeline_llm import escape_stray_quotes, parse_json
    d = parse_json(BROKEN)
    assert isinstance(d, dict) and d["details"][0] == "Серый журнал учёта «Театр \"Подвал\"», вырвана страница за пятницу"
    ok = '{"a": "x", "b": ["y", "z"], "c": {"d": "e"}}'
    assert escape_stray_quotes(ok) == ok and parse_json('{"a": "он сказал \\"нет\\""}') == {"a": 'он сказал "нет"'}


def test_broken_analysis_reaches_state(project_id):
    from engine.db import get_state, update_state
    from engine.db_state import merge_analysis_into_state
    update_state(project_id, "## ПЕРСОНАЖИ\n", "## СЮЖЕТ\n", "")
    r = merge_analysis_into_state(project_id, BROKEN, 1)
    assert r["changed"] and "Ника" in get_state(project_id)["global_state"]


def test_unparsable_json_is_an_error_not_applied(project_id, monkeypatch):
    """Не разобрать никак — ошибка; «Применить» не помечает анализ применённым."""
    from engine.db import get_pending_updates, save_state_update
    from engine.db_settings import set_active_project
    from engine.db_state import merge_analysis_into_state
    from web.app import app
    hopeless = '{"global_state_changes": [{"name": "Ника", "состояние": "оборвано'
    r = merge_analysis_into_state(project_id, hopeless, 1)
    assert not r["changed"] and "не разобран" in r["error"]
    uid = save_state_update(project_id, 1, hopeless)
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    resp = app.test_client().post(f"/state/apply/{uid}", json={})
    assert resp.status_code == 422 and uid in [u["id"] for u in get_pending_updates(project_id)]


def test_accept_retries_broken_analysis_once(project_id, monkeypatch):
    from unittest.mock import patch
    from engine.db import get_pending_updates, get_state, save_state_update, update_state
    import web.blueprints.generate_pipeline as gp
    monkeypatch.setenv("NANO_GPT_API_KEY", "k")
    update_state(project_id, "## ПЕРСОНАЖИ\n", "## СЮЖЕТ\n", "")
    good = json.dumps({"global_state_changes": [{"name": "Соня", "состояние": "смеётся"}]}, ensure_ascii=False)
    answers = iter(['{"global_state_changes": [{"name": "Ника", "состояние": "оборвано', good])
    with patch("engine.state.analyze_chapter",
               side_effect=lambda pid, ch, m: {"update_id": save_state_update(pid, ch, next(answers))}):
        assert gp._try_state_update_after_accept(project_id, 1, "nano_gpt::w/w")
    assert "Соня" in get_state(project_id)["global_state"] and not get_pending_updates(project_id)


def test_accept_reports_state_failure(project_id, monkeypatch):
    """«Последний рейс», гл.1 (24.10): битый JSON дважды — окно «Принять» должно это сказать, а не «готово»."""
    from unittest.mock import patch
    from engine.db import save_state_update, update_state
    import web.blueprints.generate_pipeline as gp
    monkeypatch.setenv("NANO_GPT_API_KEY", "k")
    update_state(project_id, "## ПЕРСОНАЖИ\n", "## СЮЖЕТ\n", "")
    cut = '{"global_state_changes": [{"name": "Ника", "состояние": "оборвано'
    failed = []
    with patch("engine.state.analyze_chapter",
               side_effect=lambda pid, ch, m: {"update_id": save_state_update(pid, ch, cut)}):
        assert not gp._try_state_update_after_accept(project_id, 1, "nano_gpt::w/w", on_fail=failed.append)
    assert failed and "State не обновлён" in failed[0]


def test_state_analysis_has_room_for_a_full_first_chapter(project_id, monkeypatch):
    """4096 токенов обрезали JSON анализа первой главы (Sonnet по ключу, 24.10)."""
    from unittest.mock import patch
    from engine.db import save_chapter
    from engine.state import analyze_chapter
    save_chapter(project_id, 1, "Текст главы. " * 50, "Глава 1")
    seen = {}
    with patch("engine.state.call_model", side_effect=lambda *a, **k: seen.update(k) or "{}"):
        analyze_chapter(project_id, 1, "anthropic_direct::claude-sonnet-5-5")
    assert seen["max_tokens"] == 0                       # без потолка (автор, 24.10)


def test_zero_means_no_cap(monkeypatch):
    """max_tokens=0 — наибольший ответ модели; SDK получает явный тайм-аут, иначе отказывает."""
    import engine.api as api
    sent = {}
    block = MagicMock(); block.type = "text"; block.text = "{}"
    msg = MagicMock(content=[block], stop_reason="end_turn", usage=MagicMock(input_tokens=1, output_tokens=1))
    client = MagicMock(); client.messages.create.side_effect = lambda **kw: (sent.update(kw), msg)[1]
    monkeypatch.setattr(api, "anthropic", MagicMock(Anthropic=lambda **k: client))
    monkeypatch.setattr(api, "_record_usage", lambda *a, **k: None)
    api.call_model("anthropic_direct::claude-sonnet-5-5", "s", "u", anthropic_key="k", max_tokens=0)
    assert sent["max_tokens"] == api.NO_CAP_TOKENS and sent["timeout"] >= 600
