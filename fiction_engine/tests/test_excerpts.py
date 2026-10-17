"""Отрывки прошлых глав для писателя (engine/excerpts, шаг 3 ENGINE_BOOST)."""
CH1 = ("Утро было серым.\n\n"
       "Ирина сняла бобровую шубу с каракулевым воротником и повесила на крюк у двери.\n\n"
       "На третьем этаже, в квартире двенадцать, пахло мокрой штукатуркой и керосином.\n\n"
       "Кот спал на подоконнике и не проснулся, когда хлопнула дверь, хотя дверь хлопнула громко.")


def test_first_chapter_gets_nothing(project_id):
    from engine.excerpts import excerpts_block
    assert excerpts_block(project_id, 1, "Ирина в шубе") == ""


def test_picks_paragraphs_about_task_entities(project_id):
    from engine.db import save_chapter
    from engine.excerpts import EXCERPTS_HEADER, excerpts_block
    save_chapter(project_id, 1, CH1, "Глава 1")
    b = excerpts_block(project_id, 2, "Глава 2. Ирина возвращается в квартиру на третьем этаже за шубой.")
    assert b.startswith(EXCERPTS_HEADER)
    assert "каракулевым воротником" in b and "квартире двенадцать" in b
    assert "Кот спал" not in b                      # ни одного слова задачи


def test_budget_and_order(project_id):
    from engine.db import save_chapter
    from engine.excerpts import excerpts_block
    save_chapter(project_id, 1, "\n\n".join(f"Ирина и шуба, абзац {i}. " + "слово " * 60 for i in range(30)), "1")
    save_chapter(project_id, 2, "Ирина снова в шубе. " * 5, "2")
    b = excerpts_block(project_id, 3, "Ирина и шуба", max_chars=1500)
    body = b.split("\n\n", 1)[1]
    assert len(body) <= 1500 + 200 and body.index("[гл.1]") < body.index("[гл.2]")


def test_off_by_default_and_setting_turns_on(project_id, monkeypatch):
    from engine.db import save_chapter, set_setting
    from engine.pipeline_context import build_context
    monkeypatch.delenv("FE_EXCERPTS", raising=False)
    save_chapter(project_id, 1, CH1, "Глава 1")
    assert "ОТРЫВКИ ПРОШЛЫХ ГЛАВ" not in build_context(project_id, 2, "Ирина за шубой.", "quick")
    set_setting("excerpts_enabled", "1")
    assert "ОТРЫВКИ ПРОШЛЫХ ГЛАВ" in build_context(project_id, 2, "Ирина за шубой.", "quick")


def test_writer_context_carries_excerpts_and_ablation_removes_them(project_id, monkeypatch):
    monkeypatch.setenv("FE_EXCERPTS", "1")
    from engine.db import save_chapter
    from engine.pipeline_context import build_context
    import engine.excerpts as ex
    save_chapter(project_id, 1, CH1, "Глава 1")
    ctx = build_context(project_id, 2, "Ирина возвращается за бобровой шубой.", "quick")
    assert "ОТРЫВКИ ПРОШЛЫХ ГЛАВ" in ctx and "каракулевым" in ctx
    monkeypatch.setattr(ex, "excerpts_block", lambda *a, **k: "")
    assert "ОТРЫВКИ ПРОШЛЫХ ГЛАВ" not in build_context(project_id, 2, "Ирина возвращается за шубой.", "quick")
