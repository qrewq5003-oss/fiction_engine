"""Маршруты планировщика: страницы отвечают, API работает."""

import json

import pytest


class TestPages:
    @pytest.mark.parametrize("path", ["/board", "/map", "/stats", "/export", "/projects"])
    def test_page_responds(self, client, path):
        resp = client.get(path, follow_redirects=True)
        assert resp.status_code == 200, f"{path} → {resp.status_code}"

    def test_root_redirects_to_board(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (301, 302)
        assert "/board" in resp.headers["Location"]

    def test_no_page_returns_500(self, client):
        """Ни одна страница без параметров не должна падать."""
        import app as planner_app
        broken = []
        for rule in planner_app.app.url_map.iter_rules():
            if rule.arguments or "GET" not in (rule.methods or set()):
                continue
            if str(rule).startswith("/static"):
                continue
            r = client.get(str(rule), follow_redirects=True)
            if r.status_code >= 500:
                broken.append((str(rule), r.status_code))
        assert not broken, f"страницы падают: {broken}"


class TestSceneApi:
    def test_create_scene(self, client, project_id):
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        resp = client.post("/api/scenes/new", json={"act_id": None})
        assert resp.status_code == 200
        assert json.loads(resp.data).get("ok") or "id" in json.loads(resp.data)

    def test_list_scenes(self, client, project_id):
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        assert client.get("/api/scenes").status_code == 200

    # api_bp зарегистрирован с url_prefix="/api"
    def test_acts_listed(self, client, project_id):
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        resp = client.get("/api/acts")
        assert resp.status_code == 200
        assert len(json.loads(resp.data).get("acts", [])) == 3

    def test_scene_page(self, client, project_id):
        from engine.db import create_scene
        sid = create_scene(project_id)
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        assert client.get(f"/scene/{sid}").status_code == 200

    def test_scene_save(self, client, project_id):
        from engine.db import create_scene, get_scene
        sid = create_scene(project_id)
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        # обработчик читает request.json, а не форму
        client.post(f"/scene/{sid}/save", json={"title": "Новое название"})
        assert get_scene(sid)["title"] == "Новое название"


class TestStatus:
    def test_status_without_fe(self, client):
        """
        Fiction Engine не запущен — это штатное состояние, а не ошибка.
        Раньше /status лез в projects.db чужого приложения; теперь
        спрашивает по HTTP и спокойно переживает отказ.
        """
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["fe_server"] is False
        assert data["has_keys"] is False

    def test_status_does_not_read_fe_database(self, client, monkeypatch):
        """Прямого обращения к БД Fiction Engine быть не должно."""
        import sqlite3
        opened = []
        real_connect = sqlite3.connect

        def spy(path, *a, **kw):
            opened.append(str(path))
            return real_connect(path, *a, **kw)

        monkeypatch.setattr(sqlite3, "connect", spy)
        client.get("/api/status")
        assert not any("fiction_engine" in p and "projects.db" in p for p in opened), opened
