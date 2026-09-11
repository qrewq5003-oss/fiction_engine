"""Слой данных планировщика: проекты, акты, сцены, связи, снапшоты."""

import pytest


class TestProjects:
    def test_create_and_read(self):
        from engine.db import create_project, get_project
        pid = create_project("Роман", "фэнтези", "о драконах")
        p = get_project(pid)
        assert p["name"] == "Роман" and p["genre"] == "фэнтези"

    def test_list(self):
        from engine.db import create_project, get_projects
        create_project("Первый"); create_project("Второй")
        assert len(get_projects()) == 2

    def test_missing_returns_none(self):
        from engine.db import get_project
        assert get_project(9999) is None

    def test_update(self, project_id):
        from engine.db import update_project, get_project
        update_project(project_id, "Новое", "хоррор", "другое описание")
        p = get_project(project_id)
        assert p["name"] == "Новое" and p["genre"] == "хоррор"

    def test_delete_removes_project(self, project_id):
        from engine.db import delete_project, get_project
        delete_project(project_id)
        assert get_project(project_id) is None

    def test_new_project_gets_default_acts(self, project_id):
        """При создании проекта заводятся три акта по умолчанию."""
        from engine.db import get_acts
        acts = get_acts(project_id)
        assert len(acts) == 3
        assert [a["number"] for a in acts] == [1, 2, 3]


class TestActs:
    def test_save_new(self, project_id):
        from engine.db import save_act, get_acts
        save_act(project_id, None, 4, "Эпилог", "#888")
        assert any(a["title"] == "Эпилог" for a in get_acts(project_id))

    def test_save_updates_existing(self, project_id):
        from engine.db import save_act, get_acts
        act = get_acts(project_id)[0]
        save_act(project_id, act["id"], act["number"], "Переименован", "#111")
        assert get_acts(project_id)[0]["title"] == "Переименован"

    def test_delete(self, project_id):
        from engine.db import get_acts, delete_act
        act = get_acts(project_id)[0]
        delete_act(act["id"])
        assert act["id"] not in [a["id"] for a in get_acts(project_id)]


class TestScenes:
    def test_create_and_get(self, project_id):
        from engine.db import create_scene, get_scene
        sid = create_scene(project_id)
        assert get_scene(sid)["project_id"] == project_id

    def test_update_fields(self, project_id):
        from engine.db import create_scene, update_scene, get_scene
        sid = create_scene(project_id)
        update_scene(sid, {"title": "Погоня", "location": "крыша",
                           "what_happens": "герой убегает"})
        s = get_scene(sid)
        assert s["title"] == "Погоня" and s["location"] == "крыша"

    def test_list_for_project(self, project_id):
        from engine.db import create_scene, get_scenes
        create_scene(project_id); create_scene(project_id)
        assert len(get_scenes(project_id)) == 2

    def test_delete(self, project_id):
        from engine.db import create_scene, delete_scene, get_scene
        sid = create_scene(project_id)
        delete_scene(sid)
        assert get_scene(sid) is None

    def test_move_between_acts(self, project_id):
        from engine.db import create_scene, get_acts, move_scene, get_scene
        sid = create_scene(project_id)
        target = get_acts(project_id)[2]
        move_scene(sid, target["id"], 0)
        assert get_scene(sid)["act_id"] == target["id"]

    def test_missing_scene_returns_none(self):
        from engine.db import get_scene
        assert get_scene(9999) is None


class TestLinks:
    def _two_scenes(self, project_id):
        from engine.db import create_scene
        return create_scene(project_id), create_scene(project_id)

    def test_save_and_list(self, project_id):
        from engine.db import save_link, get_links
        a, b = self._two_scenes(project_id)
        save_link(a, b, "cause", "потому что")
        links = get_links(project_id)
        assert len(links) == 1 and links[0]["link_type"] == "cause"

    def test_delete(self, project_id):
        from engine.db import save_link, delete_link, get_links
        a, b = self._two_scenes(project_id)
        lid = save_link(a, b, "parallel")
        delete_link(lid)
        assert get_links(project_id) == []

    def test_deleting_scene_drops_its_links(self, project_id):
        """Внешние ключи включены — связи удалённой сцены не остаются."""
        from engine.db import save_link, delete_scene, get_links
        a, b = self._two_scenes(project_id)
        save_link(a, b, "cause")
        delete_scene(a)
        assert get_links(project_id) == []


class TestSnapshots:
    def test_created_on_update(self, project_id):
        from engine.db import create_scene, update_scene, get_snapshots
        sid = create_scene(project_id)
        update_scene(sid, {"title": "Версия 1"})
        update_scene(sid, {"title": "Версия 2"})
        assert len(get_snapshots(sid)) >= 1

    def test_trimmed_to_ten(self, project_id):
        """Хранится не больше десяти снапшотов на сцену."""
        from engine.db import create_scene, update_scene, get_snapshots
        sid = create_scene(project_id)
        for i in range(15):
            update_scene(sid, {"title": f"Версия {i}"})
        assert len(get_snapshots(sid)) <= 10
