"""«Пока не раскрывать» у сцены (миграция 7): писателю — запретом в плане главы."""


def test_hold_saved_and_goes_to_plan_once(client, project_id):
    from engine.db import create_scene, get_scene, update_scene
    from web.blueprints.api_bp import plan_text
    a, b = create_scene(project_id), create_scene(project_id)
    with client.session_transaction() as sess:
        sess["project_id"] = project_id
    client.post(f"/scene/{a}/save", json={"title": "Калоши", "hold": "связь Кравец с журналом"})
    update_scene(b, {"title": "Версия Кравец", "hold": "связь Кравец с журналом"})
    assert get_scene(a)["hold"] == "связь Кравец с журналом"
    assert "связь Кравец с журналом" in client.get(f"/scene/{a}").get_data(as_text=True)
    t = plan_text([get_scene(a), get_scene(b)], 4)
    assert "ПОКА НЕ РАСКРЫВАТЬ" in t and t.count("связь Кравец с журналом") == 1
    assert t.index("СЦЕНА 2") < t.index("ПОКА НЕ РАСКРЫВАТЬ")


def test_no_hold_no_block(project_id):
    from engine.db import create_scene, get_scene, update_scene
    from web.blueprints.api_bp import plan_text
    a = create_scene(project_id)
    update_scene(a, {"title": "Паром"})
    assert "ПОКА НЕ РАСКРЫВАТЬ" not in plan_text([get_scene(a)], 1)
