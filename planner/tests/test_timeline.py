"""Проверка времени в плане без модели (engine/timeline.py)."""

import pytest

from engine.timeline import check, parse


def _plan(*times):
    return [{"id": i, "title": f"С{i}", "time_of_day": t} for i, t in enumerate(times, 1)]


def _msgs(*times):
    return [w["message"] for w in check(_plan(*times))]


class TestParse:
    @pytest.mark.parametrize("text, wd", [
        ("утро понедельника", 0), ("Вторник, 18:40", 1), ("в среду вечером", 2),
        ("четверг", 3), ("ночь на пятницу", 4), ("суббота", 5), ("воскресенье, полдень", 6),
        ("вечер", None), ("среди ночи", None),
    ])
    def test_weekday(self, text, wd):
        assert parse(text)["weekday"] == wd

    def test_date_words_and_digits(self):
        assert parse("12 октября, ночь")["date"] == (10, 12)
        assert parse("14.03, утро")["date"] == (3, 14)

    def test_clock_over_part(self):
        assert parse("вечер, 21:15")["minutes"] == 21 * 60 + 15
        assert parse("утро")["minutes"] < parse("вечер")["minutes"] < parse("ночь")["minutes"]

    def test_next_day_is_not_daytime(self):
        p = parse("на следующий день")
        assert p["next_day"] and p["minutes"] is None
        assert parse("наутро")["next_day"] and parse("наутро")["minutes"] == 8 * 60

    def test_flashback(self):
        assert parse("флешбэк: лето 1998")["flashback"]
        assert parse("за год до убийства")["flashback"]


class TestCheck:
    def test_clean_plan_is_silent(self):
        assert _msgs("понедельник, утро", "понедельник, вечер", "вторник, 9:00",
                     "на следующий день", "пятница", "понедельник") == []

    def test_weekday_jump(self):
        m = _msgs("четверг", "вторник")
        assert len(m) == 1 and "перепутан" in m[0]

    def test_gap_word_allows_jump(self):
        assert _msgs("четверг", "через пять дней, вторник") == []

    def test_next_day_wrong_weekday(self):
        m = _msgs("среда, вечер", "на следующий день, суббота")
        assert len(m) == 1 and "следующий день" in m[0]

    def test_date_backwards(self):
        m = _msgs("12 октября", "10 октября")
        assert len(m) == 1 and "раньше" in m[0]

    def test_date_and_weekday_disagree(self):
        m = _msgs("12 октября, вторник", "14 октября, пятница")
        assert len(m) == 1 and "не сходятся" in m[0]
        assert _msgs("12 октября, вторник", "14 октября, четверг") == []

    def test_same_day_time_backwards(self):
        m = _msgs("вторник, 18:00", "вторник, утро")
        assert len(m) == 1 and "время раньше" in m[0]

    def test_time_without_day_not_compared(self):
        # «вечер», потом «утро» — обычно уже следующий день
        assert _msgs("вечер", "утро") == []

    def test_undated_scene_breaks_same_day(self):
        assert _msgs("вторник, вечер", "ночь", "вторник, утро") == []

    def test_flashback_skipped(self):
        assert _msgs("четверг", "воспоминание: понедельник", "четверг, вечер") == []

    def test_warning_names_scene(self):
        w = check(_plan("четверг", "вторник"))[0]
        assert w["scene_id"] == 2 and w["title"] == "С2" and "«С1»" in w["message"]


class TestRoutes:
    def _scenes(self, pid, *times):
        from engine.db import create_scene, get_acts, update_scene
        act = get_acts(pid)[0]["id"]
        ids = []
        for i, t in enumerate(times):
            sid = create_scene(pid, act)
            update_scene(sid, {"title": f"С{i + 1}", "time_of_day": t, "position": i})
            ids.append(sid)
        return ids

    def _login(self, client, pid):
        with client.session_transaction() as sess:
            sess["project_id"] = pid

    def test_api_returns_warnings(self, client, project_id):
        ids = self._scenes(project_id, "четверг", "вторник")
        self._login(client, project_id)
        r = client.get("/api/timeline?ids=" + ",".join(map(str, ids))).get_json()
        assert len(r["warnings"]) == 1 and r["warnings"][0]["scene_id"] == ids[1]

    def test_api_drops_foreign_scenes(self, client, project_id):
        from engine.db import create_project
        other = create_project("Чужой", "хоррор")
        foreign = self._scenes(other, "четверг", "вторник")
        self._login(client, project_id)
        r = client.get("/api/timeline?ids=" + ",".join(map(str, foreign))).get_json()
        assert r["warnings"] == []

    def test_stats_page_shows_warnings(self, client, project_id):
        self._scenes(project_id, "12 октября", "10 октября")
        self._login(client, project_id)
        html = client.get("/stats").get_data(as_text=True)
        assert "Время в плане" in html and "раньше" in html