"""
test_db_projects.py — тесты db_projects.py

Покрываем: CRUD проектов, глав, state engine, L3 memory,
голосовые профили, символы, pipeline, базу знаний.
"""

import pytest
import json


# ─── Проекты ─────────────────────────────────────────────────────────────────

class TestProjects:
    def test_create_project(self, use_temp_db):
        from engine.db_projects import create_project, get_project
        pid = create_project("Моя книга", "фэнтези")
        assert isinstance(pid, int)
        p = get_project(pid)
        assert p["name"] == "Моя книга"
        assert p["genre"] == "фэнтези"

    def test_create_project_initialises_state(self, use_temp_db):
        """При создании проекта создаётся запись state_engine."""
        from engine.db_projects import create_project, get_state
        pid = create_project("Проект со стейтом")
        state = get_state(pid)
        assert "global_state" in state
        assert len(state["global_state"]) > 0

    def test_get_projects_returns_list(self, use_temp_db):
        from engine.db_projects import create_project, get_projects
        create_project("Книга 1")
        create_project("Книга 2")
        projects = get_projects()
        assert len(projects) == 2

    def test_get_project_nonexistent_returns_none(self, use_temp_db):
        from engine.db_projects import get_project
        assert get_project(9999) is None

    def test_delete_project(self, project_id):
        from engine.db_projects import delete_project, get_project
        delete_project(project_id)
        assert get_project(project_id) is None

    def test_delete_project_clears_chapters(self, project_with_chapters):
        from engine.db_projects import delete_project, get_chapters
        delete_project(project_with_chapters)
        assert get_chapters(project_with_chapters) == []


# ─── Главы ───────────────────────────────────────────────────────────────────

class TestChapters:
    def test_save_and_get_chapter(self, project_id):
        from engine.db_projects import save_chapter, get_chapter
        save_chapter(project_id, 1, "Текст первой главы", "Пролог")
        ch = get_chapter(project_id, 1)
        assert ch["content"] == "Текст первой главы"
        assert ch["title"] == "Пролог"

    def test_save_chapter_counts_words(self, project_id):
        from engine.db_projects import save_chapter, get_chapter
        save_chapter(project_id, 1, "одно два три четыре пять")
        ch = get_chapter(project_id, 1)
        assert ch["word_count"] == 5

    def test_save_chapter_upsert(self, project_id):
        """Повторное сохранение обновляет, не дублирует."""
        from engine.db_projects import save_chapter, get_chapter, get_chapters
        save_chapter(project_id, 1, "Первая версия")
        save_chapter(project_id, 1, "Обновлённая версия")
        assert len(get_chapters(project_id)) == 1
        assert get_chapter(project_id, 1)["content"] == "Обновлённая версия"

    def test_get_chapters_ordered(self, project_with_chapters):
        from engine.db_projects import get_chapters
        chapters = get_chapters(project_with_chapters)
        nums = [c["number"] for c in chapters]
        assert nums == sorted(nums)

    def test_get_last_chapters_content(self, project_with_chapters):
        from engine.db_projects import get_last_chapters_content
        last = get_last_chapters_content(project_with_chapters, n=2)
        assert len(last) == 2
        assert last[-1]["number"] == 3

    def test_get_chapter_nonexistent(self, project_id):
        from engine.db_projects import get_chapter
        assert get_chapter(project_id, 999) is None


# ─── State Engine ─────────────────────────────────────────────────────────────

class TestStateEngine:
    def test_get_state_returns_defaults_for_new_project(self, project_id):
        from engine.db_projects import get_state
        state = get_state(project_id)
        assert "global_state" in state
        assert "plot_matrix" in state
        assert "memory_graph" in state

    def test_update_state_persists(self, project_id):
        from engine.db_projects import update_state, get_state
        update_state(project_id, global_state="## Новый стейт", _snapshot_reason="тест")
        state = get_state(project_id)
        assert state["global_state"] == "## Новый стейт"

    def test_update_state_partial(self, project_id):
        """Обновление одного поля не затирает остальные."""
        from engine.db_projects import update_state, get_state
        update_state(project_id, global_state="глобал", plot_matrix="плот")
        update_state(project_id, memory_graph="память")
        state = get_state(project_id)
        assert state["global_state"] == "глобал"
        assert state["plot_matrix"] == "плот"
        assert state["memory_graph"] == "память"

    def test_snapshot_state(self, project_id):
        from engine.db_projects import update_state, snapshot_state, get_state_history
        update_state(project_id, global_state="версия 1")
        snapshot_state(project_id, reason="перед правкой")
        history = get_state_history(project_id)
        assert len(history) >= 1

    def test_restore_state_snapshot(self, project_id):
        from engine.db_projects import (update_state, snapshot_state,
                                         get_state_history, restore_state_snapshot,
                                         get_state)
        update_state(project_id, global_state="оригинал")
        snapshot_state(project_id, reason="сохраняю")
        update_state(project_id, global_state="изменено")

        # get_state_history отдаёт ORDER BY id DESC, то есть новые сверху.
        # history[-1] — самый СТАРЫЙ снапшот (авто-снапшот с шаблоном по
        # умолчанию, который делает первый update_state), а не тот, что
        # только что сняли. Ищем свой по причине — это однозначно.
        history = get_state_history(project_id)
        snap_id = next(h["id"] for h in history if h["reason"] == "сохраняю")
        restore_state_snapshot(project_id, snap_id)
        state = get_state(project_id)
        assert state["global_state"] == "оригинал"

    def test_restore_nonexistent_snapshot_returns_false(self, project_id):
        from engine.db_projects import restore_state_snapshot
        assert restore_state_snapshot(project_id, 99999) is False

    def test_parse_structured_state_extracts_characters(self, project_id):
        from engine.db_projects import update_state, get_structured_state
        global_text = """## ПЕРСОНАЖИ

### Алиса
СОСТОЯНИЕ: усталая
ЛОКАЦИЯ: лес
ЦЕЛЬ_СЕЙЧАС: найти дорогу домой
ЦЕЛЬ_ГЛУБИННАЯ: обрести покой
ЗНАЕТ: магия существует
НЕ_ЗНАЕТ: она сама маг
ИЗМЕНЕНИЕ: Гл.1
"""
        update_state(project_id, global_state=global_text)
        structured = get_structured_state(project_id)
        assert "Алиса" in structured["char_names"]
        assert structured["characters"]["Алиса"]["state"] == "усталая"
        assert structured["characters"]["Алиса"]["location"] == "лес"

    def test_parse_structured_state_handles_corrupt_data(self, project_id):
        """parse_structured_state не падает на мусорных данных."""
        from engine.db_projects import update_state, get_structured_state
        update_state(project_id, global_state="}{][мусор{{{")
        result = get_structured_state(project_id)
        assert isinstance(result, dict)
        assert "characters" in result


# ─── L3 Memory ────────────────────────────────────────────────────────────────

class TestL3Memory:
    def test_save_and_get_l3_summary(self, project_id):
        from engine.db_projects import save_l3_summary, get_l3_summary
        summary = {
            "events": "герой вышел из дому",
            "characters": "герой",
            "conflicts": "нет",
            "promises": "вернётся к закату",
            "mood": "тревожный",
        }
        save_l3_summary(project_id, 1, summary)
        result = get_l3_summary(project_id, 1)
        assert result is not None
        assert result["events"] == "герой вышел из дому"
        assert result["mood"] == "тревожный"

    def test_get_l3_summary_nonexistent(self, project_id):
        from engine.db_projects import get_l3_summary
        assert get_l3_summary(project_id, 99) is None

    def test_get_l3_summaries_range(self, project_id):
        from engine.db_projects import save_l3_summary, get_l3_summaries
        for i in range(1, 6):
            save_l3_summary(project_id, i, {"mood": f"гл{i}", "events": "", "characters": "", "conflicts": "", "promises": ""})
        result = get_l3_summaries(project_id, before_chapter=4, n=3)
        assert len(result) == 3
        assert all(s["chapter_num"] < 4 for s in result)

    def test_get_l3_active_promises_legacy_string(self, project_id):
        """Legacy строка в promises — normalize_promises конвертирует, текст виден."""
        from engine.db_projects import save_l3_summary, get_l3_active_promises
        save_l3_summary(project_id, 1, {
            "events": "", "characters": "", "conflicts": "",
            "promises": "герой обещал вернуться", "mood": ""
        })
        result = get_l3_active_promises(project_id, before_chapter=3)
        assert "герой обещал вернуться" in result

    def test_get_l3_active_promises_structured_list(self, project_id):
        """Новый формат promises (список) — активные показываются, закрытые нет."""
        from engine.db_projects import save_l3_summary, get_l3_active_promises
        save_l3_summary(project_id, 2, {
            "events": "", "characters": "", "conflicts": "", "mood": "",
            "promises": [
                {"id": "2_0", "text": "активное обещание",  "resolved": False},
                {"id": "2_1", "text": "закрытое обещание",  "resolved": True, "resolved_chapter": 4},
            ],
        })
        result = get_l3_active_promises(project_id, before_chapter=5)
        assert "активное обещание"  in result
        assert "закрытое обещание" not in result

    def test_get_l3_status(self, project_id):
        from engine.db_projects import save_l3_summary, get_l3_status
        save_l3_summary(project_id, 1, {"mood": "радостный", "events": "", "characters": "", "conflicts": "", "promises": ""})
        save_l3_summary(project_id, 2, {"mood": "грустный", "events": "", "characters": "", "conflicts": "", "promises": ""})
        status = get_l3_status(project_id)
        assert 1 in status
        assert status[1]["mood"] == "радостный"

    def test_delete_l3_summary(self, project_id):
        from engine.db_projects import save_l3_summary, get_l3_summary, delete_l3_summary
        save_l3_summary(project_id, 1, {"mood": "x", "events": "", "characters": "", "conflicts": "", "promises": ""})
        delete_l3_summary(project_id, 1)
        assert get_l3_summary(project_id, 1) is None


# ─── Голосовые профили ────────────────────────────────────────────────────────

class TestVoiceProfiles:
    def test_save_and_get_voice_profile(self, project_id):
        from engine.db_projects import save_voice_profile, get_voice_profiles
        save_voice_profile(project_id, "Тёмный голос", "сухой, лаконичный", source="custom")
        profiles = get_voice_profiles(project_id)
        assert len(profiles) == 1
        assert profiles[0]["name"] == "Тёмный голос"

    def test_set_active_voice(self, project_id):
        from engine.db_projects import save_voice_profile, set_active_voice, get_active_voice
        pid1 = save_voice_profile(project_id, "Голос 1", "профиль 1")
        pid2 = save_voice_profile(project_id, "Голос 2", "профиль 2")
        set_active_voice(project_id, pid2)
        active = get_active_voice(project_id)
        assert active["id"] == pid2

    def test_switch_active_voice_deactivates_previous(self, project_id):
        from engine.db_projects import (save_voice_profile, set_active_voice,
                                         get_active_voice, get_voice_profiles)
        pid1 = save_voice_profile(project_id, "Голос 1", "профиль 1")
        pid2 = save_voice_profile(project_id, "Голос 2", "профиль 2")
        set_active_voice(project_id, pid1)
        set_active_voice(project_id, pid2)
        active = get_active_voice(project_id)
        assert active["id"] == pid2
        # Только один активный
        profiles = get_voice_profiles(project_id)
        active_count = sum(1 for p in profiles if p["active"])
        assert active_count == 1

    def test_delete_voice_profile(self, project_id):
        from engine.db_projects import save_voice_profile, delete_voice_profile, get_voice_profiles
        vid = save_voice_profile(project_id, "Удаляемый", "профиль")
        assert delete_voice_profile(project_id, vid)
        assert get_voice_profiles(project_id) == []


# ─── Символы ─────────────────────────────────────────────────────────────────

class TestSymbols:
    def test_save_and_get_symbol(self, project_id):
        from engine.db_projects import save_symbol, get_symbols
        save_symbol(project_id, "Чёрный клинок", "предмет", 1, "смерть")
        symbols = get_symbols(project_id)
        assert len(symbols) == 1
        assert symbols[0]["name"] == "Чёрный клинок"

    def test_add_symbol_appearance(self, project_id):
        from engine.db_projects import save_symbol, add_symbol_appearance, get_symbols
        sid = save_symbol(project_id, "Роза", "образ", 1, "любовь")
        assert add_symbol_appearance(project_id, sid, 3, "роза упала", "утрата")
        symbols = get_symbols(project_id)
        assert len(symbols[0]["appearances"]) == 1
        assert symbols[0]["appearances"][0]["meaning"] == "утрата"

    def test_add_symbol_planned(self, project_id):
        from engine.db_projects import save_symbol, add_symbol_planned, get_symbols
        sid = save_symbol(project_id, "Зеркало", "образ", 1, "правда")
        assert add_symbol_planned(project_id, sid, 10, "разбить зеркало", "конец иллюзий")
        symbols = get_symbols(project_id)
        assert len(symbols[0]["planned"]) == 1

    def test_delete_symbol(self, project_id):
        from engine.db_projects import save_symbol, delete_symbol, get_symbols
        sid = save_symbol(project_id, "Временный", "предмет", 1, "ничто")
        assert delete_symbol(project_id, sid)
        assert get_symbols(project_id) == []

    def test_get_symbols_context_empty(self, project_id):
        from engine.db_projects import get_symbols_context
        assert get_symbols_context(project_id) == ""

    def test_get_symbols_context_nonempty(self, project_id):
        from engine.db_projects import save_symbol, get_symbols_context
        save_symbol(project_id, "Огонь", "стихия", 1, "страсть")
        ctx = get_symbols_context(project_id)
        assert "Огонь" in ctx
        assert "страсть" in ctx


# ─── База знаний ──────────────────────────────────────────────────────────────

class TestKnowledgeBase:
    def test_save_and_get_article(self, project_id):
        from engine.db_projects import kb_save, kb_get
        aid = kb_save(project_id, "Магия крови", "Кровь усиливает заклинания", tags="магия,кровь")
        article = kb_get(aid)
        assert article["title"] == "Магия крови"
        assert "кровь" in article["tags"]

    def test_kb_search_by_title(self, project_id):
        from engine.db_projects import kb_save, kb_search
        kb_save(project_id, "Магия огня", "огонь и пламя", tags="магия")
        kb_save(project_id, "История мира", "давным-давно", tags="мир")
        results = kb_search(project_id, "магия")
        assert len(results) >= 1
        assert results[0]["title"] == "Магия огня"

    def test_kb_search_empty_query(self, project_id):
        from engine.db_projects import kb_search
        assert kb_search(project_id, "") == []

    def test_kb_auto_inject(self, project_id):
        from engine.db_projects import kb_save, kb_get_auto_inject
        kb_save(project_id, "Авто", "содержимое", auto_inject=1)
        kb_save(project_id, "Ручной", "содержимое", auto_inject=0)
        auto = kb_get_auto_inject(project_id)
        assert len(auto) == 1
        assert auto[0]["title"] == "Авто"

    def test_kb_update_article(self, project_id):
        from engine.db_projects import kb_save, kb_get
        aid = kb_save(project_id, "Старый заголовок", "старый текст")
        kb_save(project_id, "Новый заголовок", "новый текст", article_id=aid)
        updated = kb_get(aid)
        assert updated["title"] == "Новый заголовок"

    def test_kb_delete(self, project_id):
        from engine.db_projects import kb_save, kb_delete, kb_get_all
        kb_save(project_id, "Удаляемый", "текст")
        aid = kb_get_all(project_id)[0]["id"]
        kb_delete(aid, project_id)
        assert kb_get_all(project_id) == []


# ─── Pipeline ─────────────────────────────────────────────────────────────────

class TestPipeline:
    def test_create_and_get_pipeline_run(self, project_id):
        from engine.db_projects import create_pipeline_run, get_pipeline_run
        run_id = create_pipeline_run(project_id, 1, "claude-3", "claude-3", "claude-3", "claude-3")
        run = get_pipeline_run(run_id)
        assert run["status"] == "running"
        assert run["chapter_num"] == 1

    def test_finish_pipeline_run(self, project_id):
        from engine.db_projects import create_pipeline_run, finish_pipeline_run, get_pipeline_run
        run_id = create_pipeline_run(project_id, 1, "m", "m", "m", "m")
        assert finish_pipeline_run(project_id, run_id, status="accepted")
        run = get_pipeline_run(run_id)
        assert run["status"] == "accepted"

    def test_save_pipeline_iteration(self, project_id):
        from engine.db_projects import (create_pipeline_run, save_pipeline_iteration,
                                          get_pipeline_iterations)
        run_id = create_pipeline_run(project_id, 1, "m", "m", "m", "m")
        save_pipeline_iteration(run_id, 1, "generate", "claude-3",
                                 "промпт", "сгенерированный текст", score=0.8)
        iterations = get_pipeline_iterations(run_id)
        assert len(iterations) == 1
        assert iterations[0]["stage"] == "generate"
        assert iterations[0]["score"] == pytest.approx(0.8)

    def test_get_pipeline_runs(self, project_id):
        from engine.db_projects import create_pipeline_run, get_pipeline_runs
        create_pipeline_run(project_id, 1, "m", "m", "m", "m")
        create_pipeline_run(project_id, 2, "m", "m", "m", "m")
        runs = get_pipeline_runs(project_id)
        assert len(runs) == 2


# ─── Генерации ────────────────────────────────────────────────────────────────

class TestGenerationHistory:
    def _insert_generation(self, project_id):
        """Вставляем запись в generation_history напрямую через БД."""
        from engine.db_core import get_conn
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO generation_history
                   (project_id, chapter_num, model, mode, task, result_text, word_count)
                   VALUES (?,?,?,?,?,?,?)""",
                (project_id, 1, "claude-3", "quality", "задание", "текст главы", 2)
            )
            return cur.lastrowid

    def test_get_generation_history(self, project_id):
        from engine.db_projects import get_generation_history
        self._insert_generation(project_id)
        history = get_generation_history(project_id)
        assert len(history) == 1

    def test_get_generation_by_id(self, project_id):
        from engine.db_projects import get_generation_by_id
        gen_id = self._insert_generation(project_id)
        gen = get_generation_by_id(gen_id)
        assert gen is not None
        assert gen["model"] == "claude-3"

    def test_save_generation_score(self, project_id):
        from engine.db_projects import save_generation_score, get_generation_by_id
        gen_id = self._insert_generation(project_id)
        assert save_generation_score(project_id, gen_id, 0.85, {"style": 0.9, "plot": 0.8})
        gen = get_generation_by_id(gen_id)
        assert gen["score"] == pytest.approx(0.85)

    def test_get_generation_history_empty(self, project_id):
        from engine.db_projects import get_generation_history
        assert get_generation_history(project_id) == []

    def test_get_generation_by_nonexistent_id(self, project_id):
        from engine.db_projects import get_generation_by_id
        assert get_generation_by_id(99999) is None


# ─── Chapter Analysis ─────────────────────────────────────────────────────────

class TestChapterAnalysis:
    def _make_analysis(self):
        return {
            "arc_progress": {"act": 1},
            "character_deltas": [{"name": "Герой", "change": "вырос"}],
            "opened_promises": ["герой вернётся"],
            "closed_promises": [],
            "causal_chains": [],
            "logical_gaps": [],
            "conflict_score": 0.7,
            "pacing_note": "быстрый темп",
            "plot_threads": {"main": "активна"},
            "analysis_quality": "ok",
        }

    def test_save_and_get_chapter_analysis(self, project_id):
        from engine.db_projects import save_chapter_analysis, get_chapter_analysis
        data = self._make_analysis()
        save_chapter_analysis(project_id, 1, data)
        result = get_chapter_analysis(project_id, 1)
        assert result is not None
        assert result["conflict_score"] == pytest.approx(0.7)
        assert result["pacing_note"] == "быстрый темп"
        assert result["opened_promises"] == ["герой вернётся"]

    def test_get_chapter_analysis_nonexistent(self, project_id):
        from engine.db_projects import get_chapter_analysis
        assert get_chapter_analysis(project_id, 99) is None

    def test_get_analyses_range(self, project_id):
        from engine.db_projects import save_chapter_analysis, get_analyses_range
        for i in range(1, 6):
            save_chapter_analysis(project_id, i, self._make_analysis())
        result = get_analyses_range(project_id, 2, 4)
        assert len(result) == 3
        assert all(2 <= r["chapter_num"] <= 4 for r in result)

    def test_get_all_logical_gaps(self, project_id):
        from engine.db_projects import save_chapter_analysis, get_all_logical_gaps
        data = self._make_analysis()
        data["logical_gaps"] = ["пропущена мотивация"]
        save_chapter_analysis(project_id, 1, data)
        gaps = get_all_logical_gaps(project_id, before_chapter=5)
        assert len(gaps) == 1
        assert gaps[0]["gaps"] == ["пропущена мотивация"]

    def test_get_all_logical_gaps_empty(self, project_id):
        from engine.db_projects import get_all_logical_gaps
        assert get_all_logical_gaps(project_id, before_chapter=10) == []
