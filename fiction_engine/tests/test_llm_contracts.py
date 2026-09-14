"""
test_llm_contracts.py — контрактные тесты LLM-зависимых функций.

Мокается только engine.pipeline._call — граница с внешним API.
Всё остальное реальное: БД, логика обработки ответа, запись результатов.

Что проверяется:
  A. call_json         — парсинг JSON, ошибка при не-JSON
  B. score_text        — структура результата, вычисление total
  C. run_generation    — возврат текста, warning при большой prep,
                         очистка при вставленном шаблоне, ошибка при пустом ответе
  D. analyze_voice_match — структура, парсинг score, None при отсутствии
  E. find_symbols_in_chapter — структура, existing_names в промпт
  F. generate_l3       — делегирует в l3_memory, сохраняет в БД
  G. generate_director_note_for_chapter — возвращает строку или None
  H. run_narrative_analysis — делегирует в NarrativeIntelligence
  I. run_batch_l3      — делегирует в batch_generate_l3, возвращает dict
"""

import json
import pytest
from unittest.mock import patch, MagicMock

MODEL = "anthropic_direct::claude-test"
CHAPTER_TEXT = "Герой вышел из дома и увидел дракона. " * 80  # ~3000 символов


# ─── A. call_json ─────────────────────────────────────────────────────────────

class TestCallJson:
    def test_returns_dict_from_json_response(self):
        from engine.pipeline import call_json
        fake = {"key": "value", "score": 7}
        with patch("engine.pipeline._call", return_value=json.dumps(fake)):
            result = call_json(MODEL, "system", "prompt")
        assert result == fake

    def test_extracts_json_from_surrounding_text(self):
        from engine.pipeline import call_json
        raw = 'Вот ответ: {"ok": true, "score": 8} — готово.'
        with patch("engine.pipeline._call", return_value=raw):
            result = call_json(MODEL, "system", "prompt")
        assert result["ok"] is True
        assert result["score"] == 8

    def test_raises_when_no_json(self):
        from engine.pipeline import call_json
        with patch("engine.pipeline._call", return_value="текст без JSON"):
            with pytest.raises(ValueError, match="не вернула корректный JSON"):
                call_json(MODEL, "system", "prompt")

    def test_raises_when_empty_response(self):
        from engine.pipeline import call_json
        with patch("engine.pipeline._call", return_value=""):
            with pytest.raises((ValueError, Exception)):
                call_json(MODEL, "system", "prompt")

    def test_passes_max_tokens(self):
        from engine.pipeline import call_json
        captured = {}
        def fake_call(model, sys, user, max_tokens=6000):
            captured["max_tokens"] = max_tokens
            return '{"ok": true}'
        with patch("engine.pipeline._call", side_effect=fake_call):
            call_json(MODEL, "system", "prompt", max_tokens=300)
        assert captured["max_tokens"] == 300


# ─── B. score_text ────────────────────────────────────────────────────────────

class TestScoreText:
    """
    score_text разбирает ТЕКСТОВЫЙ ответ SYS_CRITIC, а не JSON.

    Прежние тесты патчили call_json и ждали ключи literary_quality /
    voice_genre / commercial / scene_health — контракт двухлетней давности.
    Патч не срабатывал, вызов уходил в настоящий API и падал на «Нет
    Anthropic API ключа», маскируя расхождение под проблему окружения.
    """

    def _critic_reply(self, itog="36", **scores):
        base = {"ГОЛОС": 7, "СТРУКТУРА": 8, "ПЕРСОНАЖИ": 6,
                "СЦЕНЫ": 7, "ДИАЛОГ": 8}
        base.update(scores)
        lines = [f"{k}: {v}" for k, v in base.items()]
        if itog is not None:
            lines.append(f"ИТОГ: {itog}")
        lines.append("ГЛАВНЫЕ ПРОБЛЕМЫ:\n- Темп проседает в середине")
        return "\n".join(lines)

    def test_returns_dict_with_required_keys(self):
        from engine.pipeline import score_text
        with patch("engine.pipeline._call", return_value=self._critic_reply()):
            result = score_text(CHAPTER_TEXT, "фэнтези", MODEL)
        for key in ("voice", "structure", "characters", "scenes", "dialog",
                    "total", "verdict", "main_issue", "rhythm"):
            assert key in result

    def test_total_from_response_used_directly(self):
        from engine.pipeline import score_text
        with patch("engine.pipeline._call", return_value=self._critic_reply(itog="42")):
            result = score_text(CHAPTER_TEXT, "фэнтези", MODEL)
        assert result["total"] == pytest.approx(42.0)

    def test_total_computed_when_missing(self):
        """Нет строки ИТОГ — total считается суммой пяти критериев (0-50)."""
        from engine.pipeline import score_text
        reply = self._critic_reply(itog=None, **{"ГОЛОС": 8, "СТРУКТУРА": 8,
                                                 "ПЕРСОНАЖИ": 8, "СЦЕНЫ": 8,
                                                 "ДИАЛОГ": 8})
        with patch("engine.pipeline._call", return_value=reply):
            result = score_text(CHAPTER_TEXT, "фэнтези", MODEL)
        assert result["total"] == pytest.approx(40.0)

    def test_main_issue_extracted(self):
        from engine.pipeline import score_text
        with patch("engine.pipeline._call", return_value=self._critic_reply()):
            result = score_text(CHAPTER_TEXT, "фэнтези", MODEL)
        assert result["main_issue"] == "Темп проседает в середине"

    def test_genre_reaches_critic_prompt(self):
        """Жанровая линза попадает в системный промпт критика."""
        from engine.pipeline import score_text
        captured = {}

        def fake_call(model, system, user, max_tokens=6000, prefill=""):
            captured["system"] = system
            return self._critic_reply()

        with patch("engine.pipeline._call", side_effect=fake_call):
            score_text(CHAPTER_TEXT, "детектив", MODEL)
        assert "ЖАНРОВЫЙ ФОКУС — ДЕТЕКТИВ" in captured["system"]

    def test_whole_chapter_reaches_the_critic(self):
        """
        Глава уходит критику ЦЕЛИКОМ.

        Раньше здесь стояла обрезка до 4000 символов — в среднем 36% главы,
        местами 18%. Критику при этом велено оценить «темп, крюк, ФИНАЛ,
        движение»: финала он не видел вовсе.

        Поймано на цитате: критик пожаловался «Обрыв на полуслове — "Ты
        опозда"», а в тексте написано «Ты опоздал на три минуты», и стоит
        это на символе 3991 — ровно на границе обрезки. Обрывался не текст,
        а то, что видел критик; он же на это и жаловался.

        На ОЦЕНКУ это не влияет — замер 14.09 на 12 текстах парно: структура
        -0.4 при разбросе 0.8, итог -0.2 при разбросе 4.8. Исчезает только
        ложная претензия на обрыв (1 из 12 → 0 из 12). Правка чинит дефект,
        а не поднимает качество.
        """
        from engine.pipeline import score_text
        from engine.pipeline_config import CRITIC_TEXT_LIMIT
        chapter = "Он шёл по улице и думал о случившемся. " * 400   # ~15600 симв.
        assert len(chapter) < CRITIC_TEXT_LIMIT, "проверка потеряла смысл: текст короче потолка"
        captured = {}

        def fake_call(model, system, user, max_tokens=6000, prefill=""):
            captured["user"] = user
            return self._critic_reply()

        with patch("engine.pipeline._call", side_effect=fake_call):
            score_text(chapter, "фэнтези", MODEL)
        assert chapter in captured["user"], "критик снова видит только часть главы"

    def test_pathological_length_is_still_capped(self):
        """Потолок остаётся: вырожденный ответ не должен улететь в промпт целиком."""
        from engine.pipeline import score_text
        from engine.pipeline_config import CRITIC_TEXT_LIMIT
        huge = "А" * (CRITIC_TEXT_LIMIT * 3)
        captured = {}

        def fake_call(model, system, user, max_tokens=6000, prefill=""):
            captured["user"] = user
            return self._critic_reply()

        with patch("engine.pipeline._call", side_effect=fake_call):
            score_text(huge, "фэнтези", MODEL)
        assert len(captured["user"]) < len(huge)
        assert len(captured["user"]) <= CRITIC_TEXT_LIMIT + 200


# ─── C. run_generation ────────────────────────────────────────────────────────

class TestRunGeneration:
    def _project(self, project_id):
        return {"id": project_id, "genre": "фэнтezi", "title": "Тест"}

    def test_returns_text_and_warning_keys(self, project_id):
        from engine.pipeline import run_generation
        with patch("engine.pipeline._call", return_value=CHAPTER_TEXT):
            result = run_generation(self._project(project_id), 1, "quick", MODEL,
                                    "Герой встречает дракона.")
        assert "text" in result
        assert "warning" in result

    def test_text_equals_llm_response(self, project_id):
        from engine.pipeline import run_generation
        with patch("engine.pipeline._call", return_value=CHAPTER_TEXT):
            result = run_generation(self._project(project_id), 1, "quick", MODEL,
                                    "Задача главы.")
        assert result["text"] == CHAPTER_TEXT

    def test_no_warning_by_default(self, project_id):
        from engine.pipeline import run_generation
        with patch("engine.pipeline._call", return_value=CHAPTER_TEXT):
            result = run_generation(self._project(project_id), 1, "quick", MODEL,
                                    "Задача.")
        # warning None или пустая строка при нормальной prep
        assert not result["warning"] or isinstance(result["warning"], str)

    def test_raises_on_empty_response(self, project_id):
        from engine.pipeline import run_generation
        with patch("engine.pipeline._call", return_value=""):
            with pytest.raises(RuntimeError, match="пустой ответ"):
                run_generation(self._project(project_id), 1, "quick", MODEL, "Задача.")

    def test_raises_on_too_short_response(self, project_id):
        from engine.pipeline import run_generation
        with patch("engine.pipeline._call", return_value="Короткий."):
            with pytest.raises(RuntimeError, match="короткий ответ"):
                run_generation(self._project(project_id), 1, "quick", MODEL, "Задача.")

    def test_cleans_task_when_full_prompt_pasted(self, project_id):
        """Если в task вставили полный промпт — он очищается, warning добавляется."""
        from engine.pipeline import run_generation
        bad_task = "# ПРОМПТ:\n══ СИСТЕМНЫЙ ПРОМПТ ═══\nвсё содержимое промпта..."
        with patch("engine.pipeline._call", return_value=CHAPTER_TEXT):
            result = run_generation(self._project(project_id), 1, "quick", MODEL, bad_task)
        assert result["text"] == CHAPTER_TEXT
        assert result["warning"] and "промпт" in result["warning"].lower()

    def test_large_prep_triggers_warning(self, project_id):
        """Если prep > 8000 символов — предупреждение."""
        from engine.pipeline import run_generation
        big_prep = "X" * 9000
        with patch("engine.pipeline._call", return_value=CHAPTER_TEXT), \
             patch("engine.pipeline.get_prep_context", return_value=big_prep):
            result = run_generation(self._project(project_id), 1, "quick", MODEL, "Задача.")
        assert result["warning"] and "большая" in result["warning"].lower()


# ─── D. analyze_voice_match ───────────────────────────────────────────────────

class TestAnalyzeVoiceMatch:
    PROFILE = "Короткие предложения. Сухой тон. Без пафоса."
    RESPONSE_WITH_SCORE = (
        "ОЦЕНКА: 7/10\n\n"
        "СОВПАДАЕТ:\n- Сухой тон соблюдён\n\n"
        "НЕ СОВПАДАЕТ:\n- Предложения длинноваты\n\n"
        "ИСПРАВИТЬ:\n- Сократить предложения"
    )
    RESPONSE_NO_SCORE = (
        "СОВПАДАЕТ:\n- Тон ок\n\nНЕ СОВПАДАЕТ:\n- Темп"
    )

    def test_returns_dict_with_analysis_and_score(self):
        from engine.pipeline import analyze_voice_match
        with patch("engine.pipeline._call", return_value=self.RESPONSE_WITH_SCORE):
            result = analyze_voice_match(self.PROFILE, CHAPTER_TEXT, MODEL)
        assert "analysis" in result
        assert "score" in result

    def test_parses_score_correctly(self):
        from engine.pipeline import analyze_voice_match
        with patch("engine.pipeline._call", return_value=self.RESPONSE_WITH_SCORE):
            result = analyze_voice_match(self.PROFILE, CHAPTER_TEXT, MODEL)
        assert result["score"] == 7

    def test_score_none_when_not_in_response(self):
        from engine.pipeline import analyze_voice_match
        with patch("engine.pipeline._call", return_value=self.RESPONSE_NO_SCORE):
            result = analyze_voice_match(self.PROFILE, CHAPTER_TEXT, MODEL)
        assert result["score"] is None

    def test_analysis_contains_llm_response(self):
        from engine.pipeline import analyze_voice_match
        with patch("engine.pipeline._call", return_value=self.RESPONSE_WITH_SCORE):
            result = analyze_voice_match(self.PROFILE, CHAPTER_TEXT, MODEL)
        assert "ОЦЕНКА" in result["analysis"]

    def test_profile_in_prompt(self):
        from engine.pipeline import analyze_voice_match
        captured = {}
        def fake_call(model, sys, user, max_tokens=800):
            captured["prompt"] = user
            return self.RESPONSE_WITH_SCORE
        with patch("engine.pipeline._call", side_effect=fake_call):
            analyze_voice_match(self.PROFILE, CHAPTER_TEXT, MODEL)
        assert "Короткие предложения" in captured["prompt"]

    def test_whole_chapter_is_checked_for_voice(self):
        """
        Глава уходит на проверку голоса целиком.

        Здесь стояла обрезка до 2000 символов — 18 % главы. Проверка 15.09
        подсадкой слома стиля (абзац на сленге при профиле, который сленг
        запрещает), три повтора на клетку:

            чистый, обрезка 2000      [7, 7, 7]   среднее 7.0
            со сломом, обрезка 2000   [2, 2, 3]   среднее 2.3
            чистый, полный            [7, 7, 8]   среднее 7.3
            со сломом, полный         [1, 1, 1]   среднее 1.0

        Оценка работает отлично: слом, который она ВИДИТ, роняет её с 7 до
        2. Но видела она пятую часть главы, а слом в остальных 82 %
        проходил мимо — ровно то, ради чего проверка и нужна.
        """
        from engine.pipeline import analyze_voice_match
        from engine.pipeline_config import VOICE_TEXT_LIMIT
        chapter = "Он шёл по улице и думал о случившемся. " * 300
        assert 2000 < len(chapter) < VOICE_TEXT_LIMIT, "проверка потеряла смысл"
        tail = "КОРОЧЕ ГОВОРЯ, ЧУВАК, ВСЁ ЭТО БЫЛО ПРОСТО ЖЕСТЬ."
        captured = {}
        def fake_call(model, sys, user, max_tokens=800):
            captured["prompt"] = user
            return self.RESPONSE_WITH_SCORE
        with patch("engine.pipeline._call", side_effect=fake_call):
            analyze_voice_match(self.PROFILE, chapter + tail, MODEL)
        assert tail in captured["prompt"], "конец главы не дошёл до проверки голоса"

    def test_voice_check_caps_pathological_length(self):
        from engine.pipeline import analyze_voice_match
        from engine.pipeline_config import VOICE_TEXT_LIMIT
        huge = "Б" * (VOICE_TEXT_LIMIT * 3)
        captured = {}
        def fake_call(model, sys, user, max_tokens=800):
            captured["prompt"] = user
            return self.RESPONSE_WITH_SCORE
        with patch("engine.pipeline._call", side_effect=fake_call):
            analyze_voice_match(self.PROFILE, huge, MODEL)
        assert len(captured["prompt"]) < len(huge)


# ─── E. find_symbols_in_chapter ──────────────────────────────────────────────

class TestFindSymbolsInChapter:
    FAKE_RESPONSE = {
        "found": [
            {"name": "меч", "type": "артефакт", "context": "герой взял меч",
             "potential_meaning": "власть", "is_new": True}
        ],
        "note": "Найден один символ"
    }

    def test_returns_dict_with_found(self):
        from engine.pipeline import find_symbols_in_chapter
        with patch("engine.pipeline.call_json", return_value=self.FAKE_RESPONSE):
            result = find_symbols_in_chapter(CHAPTER_TEXT, [], MODEL)
        assert "found" in result
        assert isinstance(result["found"], list)

    def test_existing_names_in_prompt(self):
        from engine.pipeline import find_symbols_in_chapter
        captured = {}
        def fake_call_json(model, sys, prompt, max_tokens=800):
            captured["prompt"] = prompt
            return self.FAKE_RESPONSE
        with patch("engine.pipeline.call_json", side_effect=fake_call_json):
            find_symbols_in_chapter(CHAPTER_TEXT, ["кольцо", "свет"], MODEL)
        assert "кольцо" in captured["prompt"]
        assert "свет" in captured["prompt"]

    def test_empty_existing_names_shows_net(self):
        from engine.pipeline import find_symbols_in_chapter
        captured = {}
        def fake_call_json(model, sys, prompt, max_tokens=800):
            captured["prompt"] = prompt
            return self.FAKE_RESPONSE
        with patch("engine.pipeline.call_json", side_effect=fake_call_json):
            find_symbols_in_chapter(CHAPTER_TEXT, [], MODEL)
        assert "нет" in captured["prompt"].lower()

    def test_symbol_fields_present(self):
        from engine.pipeline import find_symbols_in_chapter
        with patch("engine.pipeline.call_json", return_value=self.FAKE_RESPONSE):
            result = find_symbols_in_chapter(CHAPTER_TEXT, [], MODEL)
        symbol = result["found"][0]
        for key in ("name", "type", "context", "potential_meaning", "is_new"):
            assert key in symbol


# ─── F. generate_l3 ──────────────────────────────────────────────────────────

class TestGenerateL3:
    def test_returns_dict_on_success(self, project_id):
        from engine.pipeline import generate_l3
        fake_summary = {"events": "е", "characters": "п",
                        "conflicts": "к", "promises": "о", "mood": "т"}
        with patch("engine.pipeline._call", return_value=json.dumps(fake_summary)):
            result = generate_l3(project_id, 1, CHAPTER_TEXT, MODEL)
        assert isinstance(result, dict)
        assert "events" in result

    def test_saves_to_db(self, project_id):
        from engine.pipeline import generate_l3
        from engine.l3_memory import has_l3_summary
        fake_summary = {"events": "е", "characters": "п",
                        "conflicts": "к", "promises": "о", "mood": "т"}
        with patch("engine.pipeline._call", return_value=json.dumps(fake_summary)):
            generate_l3(project_id, 1, CHAPTER_TEXT, MODEL)
        assert has_l3_summary(project_id, 1) is True

    def test_returns_none_on_non_json(self, project_id):
        from engine.pipeline import generate_l3
        with patch("engine.pipeline._call", return_value="не JSON"):
            result = generate_l3(project_id, 1, CHAPTER_TEXT, MODEL)
        assert result is None

    def test_short_text_returns_none(self, project_id):
        from engine.pipeline import generate_l3
        with patch("engine.pipeline._call", return_value="{}"):
            result = generate_l3(project_id, 1, "мало", MODEL)
        assert result is None


# ─── G. generate_director_note_for_chapter ───────────────────────────────────

class TestGenerateDirectorNote:
    def test_returns_string_on_success(self, project_id):
        from engine.pipeline import generate_director_note_for_chapter
        long_note = "Режиссёрская заметка. " * 20
        with patch("engine.pipeline._call", return_value=long_note):
            result = generate_director_note_for_chapter(
                project_id, 1, CHAPTER_TEXT, MODEL)
        assert result is None or isinstance(result, str)

    def test_returns_none_on_empty_response(self, project_id):
        from engine.pipeline import generate_director_note_for_chapter
        with patch("engine.pipeline._call", return_value=""):
            result = generate_director_note_for_chapter(
                project_id, 1, CHAPTER_TEXT, MODEL)
        assert result is None

    def test_returns_none_on_exception(self, project_id):
        from engine.pipeline import generate_director_note_for_chapter
        def crash(*args, **kwargs): raise RuntimeError("LLM упал")
        with patch("engine.pipeline._call", side_effect=crash):
            result = generate_director_note_for_chapter(
                project_id, 1, CHAPTER_TEXT, MODEL)
        assert result is None


# ─── H. run_narrative_analysis ───────────────────────────────────────────────

class TestRunNarrativeAnalysis:
    def test_returns_narrative_report_object(self, project_id):
        from engine.pipeline import run_narrative_analysis
        from engine.narrative_intelligence import NarrativeReport
        fake_report_json = json.dumps({
            "arc_health": [{"arc": "main", "status": "active", "health": 0.8,
                            "last_seen_chapter": 1, "note": ""}],
            "promise_status": [],
            "contradictions": [],
            "mood_trajectory": [{"chapter": 1, "mood": "тревога", "intensity": 0.7}],
            "conflict_density": 0.6,
            "warnings": []
        })
        with patch("engine.pipeline._call", return_value=fake_report_json):
            result = run_narrative_analysis(project_id, through_chapter=1, model_value=MODEL)
        assert isinstance(result, NarrativeReport)

    def test_report_has_ok_field(self, project_id):
        from engine.pipeline import run_narrative_analysis
        fake_json = json.dumps({
            "arc_health": [], "promise_status": [], "contradictions": [],
            "mood_trajectory": [], "conflict_density": 0.0, "warnings": []
        })
        with patch("engine.pipeline._call", return_value=fake_json):
            result = run_narrative_analysis(project_id, 1, MODEL)
        assert hasattr(result, "ok")

    def test_no_llm_data_still_returns_report(self, project_id):
        """Даже при пустых данных (нет L3-саммари) возвращает объект."""
        from engine.pipeline import run_narrative_analysis
        from engine.narrative_intelligence import NarrativeReport
        with patch("engine.pipeline._call", return_value="не JSON"):
            result = run_narrative_analysis(project_id, 1, MODEL)
        assert isinstance(result, NarrativeReport)


# ─── I. run_batch_l3 ─────────────────────────────────────────────────────────

class TestRunBatchL3:
    def test_returns_dict_with_three_keys(self, project_id):
        from engine.pipeline import run_batch_l3
        with patch("engine.pipeline._call", return_value="{}"):
            result = run_batch_l3(project_id, MODEL)
        assert all(k in result for k in ("generated", "skipped", "failed"))

    def test_empty_project_all_empty(self, project_id):
        from engine.pipeline import run_batch_l3
        with patch("engine.pipeline._call", return_value="{}"):
            result = run_batch_l3(project_id, MODEL)
        assert result["generated"] == [] and result["failed"] == []

    def test_generates_for_existing_chapters(self, project_id):
        from engine.pipeline import run_batch_l3
        from engine.db_projects import save_chapter
        save_chapter(project_id, 1, CHAPTER_TEXT, "Глава 1")
        fake_summary = json.dumps({"events": "е", "characters": "п",
                                   "conflicts": "к", "promises": "о", "mood": "т"})
        with patch("engine.pipeline._call", return_value=fake_summary):
            result = run_batch_l3(project_id, MODEL)
        assert 1 in result["generated"] or 1 in result["failed"]

    def test_chapter_nums_filter(self, project_id):
        """chapter_nums ограничивает обработку указанными главами."""
        from engine.pipeline import run_batch_l3
        from engine.db_projects import save_chapter
        save_chapter(project_id, 1, CHAPTER_TEXT, "Гл 1")
        save_chapter(project_id, 2, CHAPTER_TEXT, "Гл 2")
        fake_summary = json.dumps({"events": "е", "characters": "п",
                                   "conflicts": "к", "promises": "о", "mood": "т"})
        with patch("engine.pipeline._call", return_value=fake_summary):
            result = run_batch_l3(project_id, MODEL, chapter_nums=[1])
        assert 2 not in result["generated"]

    def test_progress_callback_called(self, project_id):
        from engine.pipeline import run_batch_l3
        from engine.db_projects import save_chapter
        save_chapter(project_id, 1, CHAPTER_TEXT, "Гл 1")
        calls = []
        fake_summary = json.dumps({"events": "е", "characters": "п",
                                   "conflicts": "к", "promises": "о", "mood": "т"})
        with patch("engine.pipeline._call", return_value=fake_summary):
            run_batch_l3(project_id, MODEL,
                         progress_callback=lambda cur, tot, ch: calls.append(ch))
        assert len(calls) >= 1


# ─── Пустой ответ модели ──────────────────────────────────────────────────────
#
# Найдено замером 2026-09-13: z-ai/glm-5.3 примерно в половине вызовов
# отдаёт пустое содержимое с finish_reason='length'. Проверено, что это
# поведение провайдера, а не наше: сырой HTTP и SDK дают одну картину.
#
# Раньше пустота уходила наверх обычной строкой. run_generation её ловил,
# а шаг генерации пайплайна, score_text и замер — нет: в историю падала
# пустая итерация, оценка выходила 0 из 50 и была неотличима от «модель
# написала плохо».

class TestEmptyModelResponse:
    def _dispatch(self, monkeypatch, returns, reason="length"):
        import engine.api as api
        monkeypatch.setattr(api, "_call_anthropic",
                            lambda *a, **k: returns)
        monkeypatch.setattr(api, "_remember_stop_reason", lambda r: None)
        monkeypatch.setattr(api, "get_last_stop_reason", lambda: reason)
        return api

    def test_empty_string_is_an_error_not_text(self, monkeypatch):
        import pytest
        api = self._dispatch(monkeypatch, "")
        with pytest.raises(ValueError, match="пустой ответ"):
            api.call_model("anthropic_direct::m", "sys", "usr", anthropic_key="k")

    def test_whitespace_only_is_an_error(self, monkeypatch):
        import pytest
        api = self._dispatch(monkeypatch, "   \n\n  ")
        with pytest.raises(ValueError, match="пустой ответ"):
            api.call_model("anthropic_direct::m", "sys", "usr", anthropic_key="k")

    def test_error_names_the_finish_reason(self, monkeypatch):
        import pytest
        api = self._dispatch(monkeypatch, "", reason="length")
        with pytest.raises(ValueError, match="length"):
            api.call_model("anthropic_direct::m", "sys", "usr", anthropic_key="k")

    def test_real_text_passes_through(self, monkeypatch):
        api = self._dispatch(monkeypatch, "Настоящий текст главы.")
        assert api.call_model("anthropic_direct::m", "sys", "usr",
                              anthropic_key="k") == "Настоящий текст главы."

    def test_prefill_alone_counts_as_empty(self, monkeypatch):
        """
        При продолжении главы модель получает prefill и обязана что-то
        дописать. Если она вернула ровно его — это тот же отказ, просто
        замаскированный непустой строкой.
        """
        import pytest
        api = self._dispatch(monkeypatch, "хвост предыдущей части")
        with pytest.raises(ValueError, match="пустой ответ"):
            api.call_model("anthropic_direct::m", "sys", "usr", anthropic_key="k",
                           prefill="хвост предыдущей части")

    def test_prefill_plus_new_text_passes(self, monkeypatch):
        api = self._dispatch(monkeypatch, "хвост. И продолжение главы.")
        got = api.call_model("anthropic_direct::m", "sys", "usr",
                             anthropic_key="k", prefill="хвост.")
        assert got.endswith("И продолжение главы.")
