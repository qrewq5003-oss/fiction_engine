"""«Откатить главу»: последняя глава целиком — State до её анализа, обещания, производное («Фон», 19.10)."""
import json

import pytest


@pytest.fixture
def client(project_id):
    from web.app import app
    from engine.db_settings import set_active_project
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


def _book(project_id):
    """Две главы: анализ гл.1 вносит деталь, анализ гл.2 — свою и закрывает обещание гл.1."""
    from engine.db import get_state, save_chapter, save_l3_summary, update_state
    from engine.db_state import merge_analysis_into_state
    update_state(project_id, "## Варя\nСостояние: спокойна", "## ЛИНИИ\nдело Ольги", "")
    for n in (1, 2):
        save_chapter(project_id, n, f"Глава {n}. " * 60, f"Глава {n}")
    save_l3_summary(project_id, 1, {"events": "Варя находит пальто", "characters": "", "conflicts": "",
                                    "promises": [{"id": "1_0", "text": "Пальто ещё всплывёт", "resolved": False}],
                                    "mood": ""})
    merge_analysis_into_state(project_id, json.dumps({"details": ["пальто — серое, без пуговицы"]}), 1)
    after_1 = get_state(project_id)["plot_matrix"]
    merge_analysis_into_state(project_id, json.dumps({"details": ["термос — серебристый"],
                                                      "resolved_promises": ["1_0"]}), 2)
    save_l3_summary(project_id, 2, {"events": "Термос", "characters": "", "conflicts": "", "promises": [], "mood": ""})
    return after_1


def test_snapshot_before_chapter(project_id):
    from engine.db_state import SNAPSHOT_BEFORE, snapshot_before_chapter, snapshot_state
    _book(project_id)
    snap = snapshot_before_chapter(project_id, 2)
    assert snap and snap["reason"] == f"{SNAPSHOT_BEFORE}2"
    # Глава 2 принята второй раз — снимок до первого раза, иначе в State останется прежний вариант
    snapshot_state(project_id, reason=f"{SNAPSHOT_BEFORE}2")
    assert snapshot_before_chapter(project_id, 2)["id"] == snap["id"]
    assert snapshot_before_chapter(project_id, 3) is None


def test_rollback_last_chapter(project_id, client):
    from engine.db import get_chapter, get_l3_summary, get_state
    after_1 = _book(project_id)
    assert "термос" in get_state(project_id)["plot_matrix"]
    assert get_l3_summary(project_id, 1)["promises"][0]["resolved"]
    # Не последняя глава — только удаление, откат State отказывает
    assert client.get("/chapter/1/rollback").get_json() == {"last": False, "snapshot": None}
    assert client.post("/chapter/1/rollback").status_code == 400
    info = client.get("/chapter/2/rollback").get_json()
    assert info["last"] and info["snapshot"]["id"]
    r = client.post("/chapter/2/rollback").get_json()
    assert r == {"ok": True, "state_restored": True, "promises_reopened": 1}
    assert get_state(project_id)["plot_matrix"].strip() == after_1.strip()
    assert get_chapter(project_id, 2) is None and get_l3_summary(project_id, 2) is None
    p = get_l3_summary(project_id, 1)["promises"][0]
    assert not p["resolved"] and p["resolved_chapter"] is None
    assert client.post("/chapter/2/rollback").status_code == 404


def test_rollback_without_snapshot_still_removes_chapter(project_id, client):
    """Глава принята до пометок снимков — State не трогается, глава и производное удаляются."""
    from engine.db import get_chapter, get_state, save_chapter, update_state
    update_state(project_id, "## Варя", "## ЛИНИИ\nдело", "")
    save_chapter(project_id, 1, "Глава. " * 60, "Глава 1")
    before = get_state(project_id)
    r = client.post("/chapter/1/rollback").get_json()
    assert r["ok"] and not r["state_restored"]
    assert get_chapter(project_id, 1) is None and get_state(project_id) == before
