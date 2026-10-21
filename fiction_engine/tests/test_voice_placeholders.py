"""Эталон голоса — только из текста книги до главы; заглушки шаблона State писателю не уходят (разбор 21.10, пакет 6)."""
PAST = "Варя посмотрела на Лёву и ничего не сказала про деньги."
GONE = "Строка из удалённой версии главы, которой больше нет."
FUTURE = "Марат подписал договор и ушёл, не оглядываясь."
PROFILE = (f"Короткие фразы, наблюдение без выводов.\n\nЭТАЛОН (из книги)\n{PAST}\n{GONE}\n{FUTURE}\n\n"
           "ЭТАЛОН ДИАЛОГА:\n— Ты куда? — Туда, где не спрашивают.")


def test_book_excerpts_only_from_chapters_before():
    from engine.pipeline_context import drop_future_excerpts
    out = drop_future_excerpts(PROFILE, [FUTURE], [PAST])
    assert PAST in out and GONE not in out and FUTURE not in out
    # Образцы встроенного профиля («ЭТАЛОН ДИАЛОГА») — не из книги, остаются
    assert "Туда, где не спрашивают" in out and "Короткие фразы" in out
    # Без глав до этой (прежний вызов) — как раньше: только будущие убираются
    assert GONE in drop_future_excerpts(PROFILE, [FUTURE])


def test_profile_for_chapter_and_voice_check(project_id, monkeypatch):
    from engine.db import save_chapter
    from engine.db_settings import set_active_project
    from engine.pipeline_context import profile_for_chapter
    save_chapter(project_id, 1, f"Начало. {PAST} Конец.", "Глава 1")
    save_chapter(project_id, 3, f"Начало. {FUTURE} Конец.", "Глава 3")
    two = profile_for_chapter(project_id, 2, PROFILE)
    assert PAST in two and GONE not in two and FUTURE not in two
    whole = profile_for_chapter(project_id, None, PROFILE)     # «Голос → Проверить» без главы
    assert PAST in whole and FUTURE in whole and GONE not in whole
    # «Голос → Проверить» сверяет с тем же эталоном
    from engine import pipeline
    from engine.db_narrative import save_voice_profile, set_active_voice
    from web.app import app
    vid = save_voice_profile(project_id, "Варя", PROFILE, "custom")
    set_active_voice(project_id, vid)
    set_active_project(project_id)
    seen = {}
    monkeypatch.setattr(pipeline, "analyze_voice_match",
                        lambda prof, text, model: seen.update(p=prof) or {"analysis": "", "score": 7})
    monkeypatch.setenv("NANO_GPT_API_KEY", "test-key")
    app.config.update(TESTING=True, FE_CSRF=False)
    r = app.test_client().post("/voice/check", json={"text": "Глава. " * 30, "model": "nano_gpt::x/y",
                                                     "chapter_num": 2})
    assert r.get_json().get("ok") and GONE not in seen["p"] and FUTURE not in seen["p"]


def test_template_placeholder_not_given_to_writer():
    """«Фон»: «НЕ_ДОЛЖНО_СЛУЧИТЬСЯ: [что нельзя допустить в следующей главе]» → «⚠ НЕЛЬЗЯ: […]»."""
    from engine.db_state import parse_structured_state
    from engine.pipeline_context import extract_relevant_state
    state = {"global_state": "## МИР\nМОМЕНТ: среда, 26 ноября\nНЕ_ДОЛЖНО_СЛУЧИТЬСЯ: [что нельзя допустить "
                             "в следующей главе]\nУГРОЗА: []\n", "plot_matrix": "", "memory_graph": ""}
    world = parse_structured_state(state)["world"]
    assert world["moment"] == "среда, 26 ноября" and world["forbidden"] == "" and world["threat"] == ""
    assert "НЕЛЬЗЯ" not in extract_relevant_state(state, "задача")
