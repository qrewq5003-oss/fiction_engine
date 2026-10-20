"""Блок голоса писателю: главы перед этой, отрывок из середины, эталоны профиля без будущих глав (обход 20.10)."""


def _chapter(n: int, paras: int = 9) -> str:
    return "\n\n".join(f"Глава {n}, абзац {i}. Варя смотрела на экран. Гоша молчал." for i in range(1, paras + 1))


def test_voice_sample_from_middle():
    from engine.pipeline_context import voice_sample
    s = voice_sample(_chapter(3), 200)
    assert s.startswith("Глава 3, абзац 5.") and len(s) <= 200
    # Абзац длиннее отрывка — режется по концу предложения
    long = "Начало. " + "Середина главы тянется. " * 40
    cut = voice_sample(long, 100)
    assert cut.endswith("тянется.") and len(cut) <= 100
    assert voice_sample("", 100) == ""


def test_drop_future_excerpts():
    from engine.pipeline_context import drop_future_excerpts
    profile = ("Первое лицо, прошедшее время.\nСцена начинается с действия.\n\n"
               "ЭТАЛОН (из книги)\nГлава 16, абзац 2. Варя смотрела на экран.\n\n"
               "— Белова велела улыбаться.\n\nСтарый эталон из второй главы остаётся.")
    future = ["Пролог. Глава 16, абзац 2. Варя смотрела на экран. — Белова велела улыбаться."]
    out = drop_future_excerpts(profile, future)
    assert "Глава 16" not in out and "Белова" not in out
    assert "Старый эталон из второй главы остаётся." in out and "Сцена начинается с действия." in out
    # Все строки эталона из будущего — заголовок тоже уходит
    assert "ЭТАЛОН" not in drop_future_excerpts(profile.rsplit("\n\n", 1)[0], future)
    # Правила профиля не трогаются, даже если фраза есть в главах
    assert drop_future_excerpts("Сцена начинается с действия.", ["Сцена начинается с действия."]) == \
        "Сцена начинается с действия."
    assert drop_future_excerpts(profile, []) == profile


def test_rewrite_sees_only_earlier_chapters(project_id):
    """Гл.3 заново в книге из пяти глав: эталон голоса — гл.1–2, не 4–5 и не её прежний текст."""
    from engine.db import save_chapter, save_voice_profile, set_active_voice
    from engine.pipeline_context import build_context
    for n in range(1, 6):
        save_chapter(project_id, n, _chapter(n), f"Глава {n}")
    vid = save_voice_profile(project_id, "Варя", "Первое лицо.\n\nЭТАЛОН (из книги)\nГлава 4, абзац 1. Варя смотрела на экран.\n"
                                            "Глава 1, абзац 1. Варя смотрела на экран.")
    set_active_voice(project_id, vid)
    ctx = build_context(project_id, 3, "Задача главы.")
    assert "[Гл.1]" in ctx and "[Гл.2]" in ctx
    for n in (3, 4, 5):
        assert f"[Гл.{n}]" not in ctx and f"Глава {n}, абзац" not in ctx
    assert "Глава 1, абзац 1." in ctx          # эталон профиля из прошлой главы остаётся


def test_analysis_promises_as_text():
    """Снимок заданий 20.10: обещания прошлых глав уходили в анализ Python-словарём."""
    from engine.chapter_analyzer import _clip_words, _promises_text
    got = _promises_text([{"id": "7_1", "text": "Варя узнает, кто взял ноутбук", "resolved": False,
                           "resolved_chapter": None},
                          {"id": "7_2", "text": "Закрытое", "resolved": True}])
    assert got == "Варя узнает, кто взял ноутбук"
    assert _promises_text("строка как есть") == "строка как есть" and _promises_text(None) == ""
    assert _clip_words("слово " * 50, 30).endswith("…") and len(_clip_words("слово " * 50, 30)) <= 31
