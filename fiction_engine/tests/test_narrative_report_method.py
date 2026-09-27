#!/usr/bin/env python3
"""
/narrative/report вызывает модель и пишет расход — поэтому только POST.

На GET его дёргали бы предзагрузка ссылки браузером, восстановление
вкладок, переход по истории — каждый раз платный анализ. Находку дал
tools/getcheck.py; тест держит маршрут и страницу в согласии.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()


def test_get_is_refused_and_post_runs(project_id, monkeypatch):
    import engine.pipeline as pipeline
    from engine.db import set_active_project
    from web.app import app
    set_active_project(project_id)
    calls = []

    def fake(pid, ch, model):
        calls.append((pid, ch))
        return MagicMock(ok=True, through_chapter=ch, arc_health={}, promise_status={},
                         contradictions=[], mood_trajectory=[], conflict_density=[],
                         warnings=[])

    monkeypatch.setattr(pipeline, "run_narrative_analysis", fake)
    client = app.test_client()
    assert client.get("/narrative/report/3").status_code == 405
    assert calls == []
    assert client.post("/narrative/report/3").status_code == 200
    assert calls == [(project_id, 3)]


def test_page_uses_post():
    html = (Path(__file__).resolve().parents[1] / "web" / "templates" / "narrative.html") \
        .read_text(encoding="utf-8")
    assert "fetch(`/narrative/report/${ch}`, {method: 'POST'})" in html
