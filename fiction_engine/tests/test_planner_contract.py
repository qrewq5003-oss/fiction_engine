#!/usr/bin/env python3
"""
Контракт с планировщиком: адреса, по которым он обращается к Fiction
Engine, обязаны существовать и отдавать ожидаемую структуру.

Тест живёт на стороне FE намеренно. Импортировать планировщик отсюда
нельзя: оба проекта держат пакеты с именами engine и web, и первый
попавший в sys.path перекрывает второй. Поэтому ожидания планировщика
вычитываются из его исходников, а проверяются на настоящем FE.

Именно на этом стыке жили три поломки, которых не видел ни один тест
по отдельности:
  /api/inline_call        — маршрута не существовало, ассистент
                            планировщика всегда получал 503;
  /api/director_note      — звался без номера главы, экспорт плана
                            молча возвращал sent: false;
  /api/project/context    — игнорировал ?pid, импортировался не тот
                            проект, который просили.
"""

import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

PLANNER_ROOT = Path(__file__).resolve().parents[2] / "planner"


def _planner_source() -> str:
    if not PLANNER_ROOT.exists():
        pytest.skip("планировщик не найден")
    return "\n".join(p.read_text(encoding="utf-8")
                     for p in PLANNER_ROOT.rglob("*.py")
                     if "__pycache__" not in str(p))


def _called_endpoints() -> set[str]:
    """Пути FE, которые планировщик дёргает в коде."""
    src = _planner_source()
    found = set()
    for m in re.finditer(r'[\'"]?\{_fe_base_url\(\)\}(/api/[\w/\-]+)', src):
        found.add(m.group(1))
    for m in re.finditer(r'f?"\{_fe_base_url\(\)\}(/api/[\w/\-]+)', src):
        found.add(m.group(1))
    return found


@pytest.fixture
def client(monkeypatch):
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "fe.db")
    from engine.db_core import init_db
    init_db()
    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    return app.test_client()


@pytest.fixture
def project(client):
    from engine.db import create_project, set_active_project, update_state
    pid = create_project("Серия", "детектив")
    set_active_project(pid)
    update_state(pid, "## ПЕРСОНАЖИ\n\n### Марк\nСОСТОЯНИЕ: жив\n",
                 "СТАТУС: завязка\n", "")
    return pid


# ─── Существование адресов ────────────────────────────────────────────────────

def test_planner_calls_are_discoverable():
    """Сам разбор исходников планировщика должен что-то находить."""
    called = _called_endpoints()
    assert called, "не удалось вычитать адреса из планировщика"


def test_every_called_endpoint_exists(client):
    """Каждый адрес, который зовёт планировщик, есть в маршрутах FE."""
    from web.app import app
    routes = {str(r) for r in app.url_map.iter_rules()}
    missing = []
    for path in sorted(_called_endpoints()):
        # Планировщик подставляет номер главы в адрес, поэтому из разбора
        # приходит префикс вида "/api/director_note/" — сопоставляем с
        # маршрутом, у которого дальше идёт параметр.
        stem = path.rstrip("/")
        if any(r == stem or r.startswith(stem + "/<") for r in routes):
            continue
        missing.append(path)
    assert not missing, f"планировщик зовёт несуществующие адреса FE: {missing}"


@pytest.mark.parametrize("path", ["/api/projects/list", "/api/keys/status"])
def test_simple_endpoints_respond(client, path):
    assert client.get(path).status_code < 400


def test_director_note_save_accepts_planner_payload(client, project):
    resp = client.post("/api/director_note/1/save", json={"note": "план главы"})
    assert resp.status_code == 200, resp.data


# ─── Структура ответов ────────────────────────────────────────────────────────

class TestProjectContext:
    def test_returns_keys_planner_reads(self, client, project):
        """Имена полей разбираются в planner/web/blueprints/api_bp.py."""
        data = json.loads(client.get("/api/project/context").data)
        assert isinstance(data.get("global_state"), str)
        assert isinstance(data.get("plot_matrix"), str)
        assert isinstance(data.get("active_promises"), list)
        assert "genre" in data["project"]

    def test_honours_pid(self, client, project):
        from engine.db import create_project
        other = create_project("Другая серия", "хоррор")
        data = json.loads(client.get(f"/api/project/context?pid={other}").data)
        assert data["project"]["id"] == other
        assert data["project"]["name"] == "Другая серия"

    def test_unknown_pid_is_404(self, client, project):
        assert client.get("/api/project/context?pid=99999").status_code == 404

    def test_without_pid_uses_active(self, client, project):
        data = json.loads(client.get("/api/project/context").data)
        assert data["project"]["id"] == project


class TestProjectsList:
    def test_shape(self, client, project):
        data = json.loads(client.get("/api/projects/list").data)
        assert data["projects"]
        for p in data["projects"]:
            assert {"id", "name", "genre"} <= set(p)


class TestInlineCall:
    def test_requires_model_and_prompt(self, client):
        assert client.post("/api/inline_call", json={}).status_code == 400

    def test_requires_api_key(self, client):
        resp = client.post("/api/inline_call",
                           json={"model": "anthropic_direct::x", "prompt": "привет"})
        assert resp.status_code == 400
        assert "ключ" in json.loads(resp.data)["error"].lower()

    def test_returns_result(self, client, monkeypatch):
        from engine.db import save_api_key
        save_api_key("anthropic_direct", "test-key")
        monkeypatch.setattr("engine.pipeline.call_llm", lambda *a, **kw: "ответ модели")
        resp = client.post("/api/inline_call", json={
            "model": "anthropic_direct::x", "prompt": "развей сцену",
            "system": "ты помощник", "max_tokens": 300,
        })
        assert resp.status_code == 200
        assert json.loads(resp.data)["result"] == "ответ модели"

    def test_rejects_bad_max_tokens(self, client):
        resp = client.post("/api/inline_call", json={
            "model": "anthropic_direct::x", "prompt": "текст", "max_tokens": "много"})
        assert resp.status_code == 400

    def test_empty_answer_is_error(self, client, monkeypatch):
        from engine.db import save_api_key
        save_api_key("anthropic_direct", "test-key")
        monkeypatch.setattr("engine.pipeline.call_llm", lambda *a, **kw: "   ")
        resp = client.post("/api/inline_call",
                           json={"model": "anthropic_direct::x", "prompt": "текст"})
        assert resp.status_code == 502
