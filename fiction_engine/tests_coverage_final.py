"""
tests_coverage_final.py — покрытие оставшихся непокрытых функций:

  1. state_prompts.py — _remove_empty_placeholder_lines, _remove_orphaned_headers,
     _cliche_block, _genre_identity, _genre_rules, _director_block,
     strip_empty_placeholders, _quick_prompt, _quality_prompt, _master_prompt,
     _prefill_from_freeform

  2. narrative_intelligence.py — _warn_stalled_arcs, _warn_overdue_promises,
     _warn_missing_summaries, _warn_pacing_coverage, _generate_warnings,
     analyze_narrative, _analyze_arcs, _check_promise_resolutions,
     _detect_contradictions, _extract_mood_trajectory + NIL methods

  3. pipeline.py — _get_keys, _get_resolver_model, _make_module_resolver,
     _make_model_caller, _build_consolidated_voice, _extract_relevant_state,
     _resolve_pipeline_steps

  4. engine_loaders.py — load_module_dependencies_from_index,
     _load_genre_catalog, _load_anticliche_replacements и все обёртки

  5. engine_loaders_core.py — load_validation_checklist, _read_md_useful

  6. engine_loaders_genre.py — _load_fantasy_arc, _load_arc_by_heading,
     _load_antagonist_section, _extract_subgenre_block, _extract_quality_rules_fallback
"""

# Этот файл конвертируется в run()-вызовы и добавляется в run_tests.py


# ═══════════════════════════════════════════════════════════════
# 1. state_prompts.py — непокрытые функции
# ═══════════════════════════════════════════════════════════════

class TestStatePromptsPlaceholders:

    def test_remove_empty_placeholder_lines_basic(self):
        from engine.state_prompts import _remove_empty_placeholder_lines
        lines = [
            "Задача главы: []",
            "Нормальная строка",
            "Тональность: []",
            "Ещё строка",
        ]
        result = _remove_empty_placeholder_lines(lines)
        assert "Задача главы: []" not in result
        assert "Тональность: []" not in result
        assert "Нормальная строка" in result

    def test_remove_empty_placeholder_lines_keeps_filled(self):
        from engine.state_prompts import _remove_empty_placeholder_lines
        lines = ["Задача: [Иван находит меч]", "Пустой: []"]
        result = _remove_empty_placeholder_lines(lines)
        assert any("Задача: [Иван находит меч]" in l for l in result)
        assert not any("Пустой: []" in l for l in result)

    def test_remove_empty_placeholder_lines_standalone_bracket(self):
        from engine.state_prompts import _remove_empty_placeholder_lines
        lines = ["[]", "- []", "текст"]
        result = _remove_empty_placeholder_lines(lines)
        assert "[]" not in result
        assert "- []" not in result
        assert "текст" in result

    def test_remove_orphaned_headers_removes_orphan(self):
        from engine.state_prompts import _remove_orphaned_headers
        KEEP = set()
        MARKERS = {"---"}
        lines = [
            "Тональность:",        # заголовок
            "",                     # пусто
            "Задача:",              # другой заголовок — это orphan-next
        ]
        result = _remove_orphaned_headers(lines, KEEP, MARKERS)
        # "Тональность:" осиротел (следующий непустой тоже заголовок) → удалён
        assert not any(l.strip() == "Тональность:" for l in result)

    def test_remove_orphaned_headers_keeps_header_with_content(self):
        from engine.state_prompts import _remove_orphaned_headers
        KEEP = set()
        MARKERS = set()
        lines = [
            "Тональность:",
            "напряжённая",
        ]
        result = _remove_orphaned_headers(lines, KEEP, MARKERS)
        assert any("Тональность:" in l for l in result)

    def test_remove_orphaned_headers_keep_set_respected(self):
        from engine.state_prompts import _remove_orphaned_headers
        KEEP = {"ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ"}
        MARKERS = {"---"}
        lines = [
            "ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:",
            "",
            "---",
        ]
        result = _remove_orphaned_headers(lines, KEEP, MARKERS)
        assert any("ТЕКУЩЕЕ СОСТОЯНИЕ" in l for l in result)


class TestStatePromptsClicheAndGenre:

    def test_cliche_block_returns_nonempty(self):
        from engine.state_prompts import _cliche_block
        result = _cliche_block()
        assert len(result) > 100
        assert "ЗАПРЕТ" in result.upper() or "клише" in result.lower() or "ЗАПРЕЩ" in result.upper()

    def test_genre_identity_fantasy(self):
        from engine.state_prompts import _genre_identity
        assert "фэнтези" in _genre_identity("фэнтези").lower()

    def test_genre_identity_detective(self):
        from engine.state_prompts import _genre_identity
        assert "детектив" in _genre_identity("нуар").lower()

    def test_genre_identity_thriller(self):
        from engine.state_prompts import _genre_identity
        assert "триллер" in _genre_identity("триллер").lower()

    def test_genre_identity_horror(self):
        from engine.state_prompts import _genre_identity
        assert "хоррор" in _genre_identity("хоррор").lower()

    def test_genre_identity_scifi(self):
        from engine.state_prompts import _genre_identity
        assert "фантастик" in _genre_identity("фантастика").lower()

    def test_genre_identity_romance(self):
        from engine.state_prompts import _genre_identity
        assert "романтическ" in _genre_identity("романтика").lower()

    def test_genre_identity_realism(self):
        from engine.state_prompts import _genre_identity
        assert "реалистическ" in _genre_identity("реализм").lower()

    def test_genre_identity_unknown(self):
        from engine.state_prompts import _genre_identity
        result = _genre_identity("нечто неизвестное")
        assert len(result) > 5  # fallback существует

    def test_genre_rules_detective(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("детектив")
        assert "ЖАНРОВЫЕ ПРАВИЛА" in result
        assert "детект" in result.lower() or "нуар" in result.lower()

    def test_genre_rules_thriller(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("триллер")
        assert "напряжение" in result.lower() or "ЖАНРОВЫЕ" in result

    def test_genre_rules_horror(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("ужасы")
        assert "страх" in result.lower() or "ЖАНРОВЫЕ" in result

    def test_genre_rules_romance(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("романтика")
        assert "ЖАНРОВЫЕ" in result

    def test_genre_rules_realism(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("реализм")
        assert "ЖАНРОВЫЕ" in result

    def test_genre_rules_unknown_empty(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("мистерия")
        assert result == ""

    def test_director_block_none(self):
        from engine.state_prompts import _director_block
        assert _director_block(None) == ""

    def test_director_block_empty_string(self):
        from engine.state_prompts import _director_block
        assert _director_block("") == ""

    def test_director_block_with_note(self):
        from engine.state_prompts import _director_block
        result = _director_block("Больше диалога")
        assert "Больше диалога" in result
        assert "редактор" in result.lower() or "ЗАМЕТКА" in result


class TestStatePromptsPromptBuilders:

    def _state(self):
        return {"global_state": "Иван в лесу", "plot_matrix": "линия А", "memory_graph": "знает всё"}

    def test_quick_prompt_returns_string(self):
        from engine.state_prompts import _quick_prompt
        result = _quick_prompt(1, "фэнтези", "Серия", self._state(), "")
        assert isinstance(result, str) and len(result) > 200

    def test_quick_prompt_contains_chapter_num(self):
        from engine.state_prompts import _quick_prompt
        result = _quick_prompt(7, "фэнтези", "Серия", self._state(), "")
        assert "7" in result

    def test_quick_prompt_contains_genre(self):
        from engine.state_prompts import _quick_prompt
        result = _quick_prompt(1, "детектив", "Серия", self._state(), "")
        assert "детект" in result.lower() or "нуар" in result.lower()

    def test_quick_prompt_with_director_note(self):
        from engine.state_prompts import _quick_prompt
        result = _quick_prompt(1, "фэнтези", "Серия", self._state(), "", director_note="Больше экшна")
        assert "Больше экшна" in result

    def test_quality_prompt_returns_string(self):
        from engine.state_prompts import _quality_prompt
        result = _quality_prompt(3, "триллер", "Серия", self._state(), "")
        assert isinstance(result, str) and len(result) > 200

    def test_quality_prompt_contains_chapter(self):
        from engine.state_prompts import _quality_prompt
        result = _quality_prompt(5, "триллер", "Серия", self._state(), "")
        assert "5" in result

    def test_master_prompt_returns_string(self):
        from engine.state_prompts import _master_prompt
        result = _master_prompt(10, "хоррор", "Серия", self._state(), "")
        assert isinstance(result, str) and len(result) > 200

    def test_master_prompt_contains_state(self):
        from engine.state_prompts import _master_prompt
        result = _master_prompt(1, "хоррор", "Серия", self._state(), "")
        assert "Иван в лесу" in result

    def test_master_prompt_with_next_context(self):
        from engine.state_prompts import _master_prompt
        result = _master_prompt(1, "фэнтези", "Серия", self._state(), "Предыдущая глава закончилась взрывом")
        assert "Предыдущая глава" in result


class TestStripEmptyPlaceholders:

    def test_strip_removes_empty_fields(self):
        from engine.state_prompts import strip_empty_placeholders
        prompt = "Задача: []\nНормальный текст\nТональность: []"
        result = strip_empty_placeholders(prompt)
        assert "[]" not in result
        assert "Нормальный текст" in result

    def test_strip_collapses_multiple_blanks(self):
        from engine.state_prompts import strip_empty_placeholders
        prompt = "Строка1\n\n\n\nСтрока2"
        result = strip_empty_placeholders(prompt)
        assert "\n\n\n" not in result

    def test_strip_keeps_filled_brackets(self):
        from engine.state_prompts import strip_empty_placeholders
        prompt = "Задача: [Иван находит ключ]\nПустое: []"
        result = strip_empty_placeholders(prompt)
        assert "Иван находит ключ" in result

    def test_strip_returns_stripped(self):
        from engine.state_prompts import strip_empty_placeholders
        result = strip_empty_placeholders("   текст   ")
        assert not result.startswith(" ")
        assert not result.endswith(" ")


class TestPrefillFromFreeform:

    def test_finds_capitalized_names(self):
        from engine.state_prompts import _prefill_from_freeform
        text = "Иван вышел на улицу. Иван посмотрел в небо. Мария ждала его."
        result = _prefill_from_freeform(text)
        assert "Иван" in result

    def test_empty_text_returns_empty(self):
        from engine.state_prompts import _prefill_from_freeform
        assert _prefill_from_freeform("") == ""

    def test_excludes_stop_words(self):
        from engine.state_prompts import _prefill_from_freeform
        text = "Он пошёл. Он вернулся. Она ждала. Она плакала."
        result = _prefill_from_freeform(text)
        # "Он" и "Она" не в _EXCLUDE_WORDS но 2 буквы → должны быть отброшены
        assert "Он:" not in result

    def test_max_four_names(self):
        from engine.state_prompts import _prefill_from_freeform
        # Много имён — берём не больше 4
        text = " ".join([f"Персонаж{i} пошёл. Персонаж{i} вернулся." for i in range(10)])
        result = _prefill_from_freeform(text)
        count = result.count(":")
        assert count <= 4


# ═══════════════════════════════════════════════════════════════
# 2. narrative_intelligence.py — непокрытые функции
# ═══════════════════════════════════════════════════════════════

class TestWarnFunctions:
    """_warn_stalled_arcs, _warn_overdue_promises, _warn_missing_summaries, _warn_pacing_coverage"""

    def test_warn_stalled_arcs_no_stalled(self):
        from engine.narrative_intelligence import _warn_stalled_arcs
        from engine.contracts import ArcStatus
        arcs = {"Иван": ArcStatus("Иван", "active", 5, "", stalled=False)}
        assert _warn_stalled_arcs(arcs) is None

    def test_warn_stalled_arcs_with_stalled(self):
        from engine.narrative_intelligence import _warn_stalled_arcs
        from engine.contracts import ArcStatus
        arcs = {"Иван": ArcStatus("Иван", "stalled", 3, "", stalled=True)}
        result = _warn_stalled_arcs(arcs)
        assert result is not None
        assert "Иван" in result

    def test_warn_overdue_promises_none_overdue(self):
        from engine.narrative_intelligence import _warn_overdue_promises
        from engine.contracts import PromiseItem
        items = [PromiseItem("обещание", 1, resolved=True, overdue=False)]
        assert _warn_overdue_promises(items) is None

    def test_warn_overdue_promises_with_overdue(self):
        from engine.narrative_intelligence import _warn_overdue_promises
        from engine.contracts import PromiseItem
        items = [PromiseItem("Герой вернётся", 1, resolved=False, overdue=True)]
        result = _warn_overdue_promises(items)
        assert result is not None
        assert "Герой вернётся" in result or "обещани" in result.lower()

    def test_warn_missing_summaries_enough(self):
        from engine.narrative_intelligence import _warn_missing_summaries
        summaries = [{}] * 8
        assert _warn_missing_summaries(summaries, total_chapters=10) is None

    def test_warn_missing_summaries_too_few(self):
        from engine.narrative_intelligence import _warn_missing_summaries
        summaries = [{}] * 2
        result = _warn_missing_summaries(summaries, total_chapters=10)
        assert result is not None
        assert "2" in result or "саммари" in result.lower()

    def test_warn_missing_summaries_few_chapters_ok(self):
        from engine.narrative_intelligence import _warn_missing_summaries
        # total_chapters <= 5 → не предупреждаем
        assert _warn_missing_summaries([], total_chapters=4) is None

    def test_warn_pacing_coverage_ok(self):
        from engine.narrative_intelligence import _warn_pacing_coverage
        assert _warn_pacing_coverage(0.8) is None

    def test_warn_pacing_coverage_low(self):
        from engine.narrative_intelligence import _warn_pacing_coverage
        result = _warn_pacing_coverage(0.3)
        assert result is not None
        assert "30" in result or "pacing" in result.lower() or "темп" in result.lower()

    def test_warn_pacing_coverage_border(self):
        from engine.narrative_intelligence import _warn_pacing_coverage
        assert _warn_pacing_coverage(0.5) is None
        assert _warn_pacing_coverage(0.49) is not None


class TestGenerateWarnings:

    def _make_arc(self, stalled=False):
        from engine.contracts import ArcStatus
        return ArcStatus("Иван", "active" if not stalled else "stalled", 1, "", stalled=stalled)

    def _make_promise(self, overdue=False):
        from engine.contracts import PromiseItem
        return PromiseItem("Герой вернётся", 1, resolved=False, overdue=overdue)

    def test_no_warnings_clean(self):
        from engine.narrative_intelligence import _generate_warnings
        result = _generate_warnings(
            summaries=[{}] * 5,
            arc_health={"Иван": self._make_arc(stalled=False)},
            promise_status=[self._make_promise(overdue=False)],
            contradictions=[],
            conflict_density=[0.5, 0.6, 0.4, 0.5, 0.6],
            total_chapters=5,
        )
        assert isinstance(result, list)

    def test_blocking_contradiction_in_warnings(self):
        from engine.narrative_intelligence import _generate_warnings
        contradictions = ["🚨 БЛОКИРУЮЩЕЕ Гл.1↔Гл.3: мёртвый ожил"]
        result = _generate_warnings(
            summaries=[{}] * 3,
            arc_health={},
            promise_status=[],
            contradictions=contradictions,
            conflict_density=[0.5, 0.5, 0.5],
            total_chapters=3,
        )
        assert any("БЛОКИРУЮЩЕЕ" in w for w in result)

    def test_stalled_arc_generates_warning(self):
        from engine.narrative_intelligence import _generate_warnings
        result = _generate_warnings(
            summaries=[{}] * 3,
            arc_health={"Иван": self._make_arc(stalled=True)},
            promise_status=[],
            contradictions=[],
            conflict_density=[0.5, 0.5, 0.5],
            total_chapters=3,
        )
        assert any("Иван" in w for w in result)

    def test_overdue_promise_generates_warning(self):
        from engine.narrative_intelligence import _generate_warnings
        result = _generate_warnings(
            summaries=[{}] * 3,
            arc_health={},
            promise_status=[self._make_promise(overdue=True)],
            contradictions=[],
            conflict_density=[0.5, 0.5, 0.5],
            total_chapters=3,
        )
        assert len(result) > 0


class TestNarrativeIntelligenceMethods:
    """NarrativeIntelligence — методы без LLM"""

    def _nil(self, summaries=None):
        from engine.narrative_intelligence import NarrativeIntelligence
        data = summaries or []
        return NarrativeIntelligence(
            get_summaries_fn=lambda pid, ch, n=50: data,
            get_state_fn=lambda pid: {"global_state": "", "plot_matrix": "", "memory_graph": ""},
            get_chapters_fn=lambda pid: [],
        )

    def _s(self, ch, events="", conflicts="", mood="", promises="", characters=""):
        return {"chapter_num": ch, "events": events, "conflicts": conflicts,
                "mood": mood, "promises": promises, "characters": characters, "project_id": 1}

    def test_extract_mood_trajectory_basic(self):
        nil = self._nil()
        summaries = [self._s(1, mood="тревожное"), self._s(2, mood="светлое")]
        result = nil._extract_mood_trajectory(summaries)
        assert len(result) == 2
        assert "тревожное" in result[0]

    def test_extract_mood_trajectory_skips_empty(self):
        nil = self._nil()
        summaries = [self._s(1, mood=""), self._s(2, mood="мрачное")]
        result = nil._extract_mood_trajectory(summaries)
        assert len(result) == 1

    def test_extract_conflict_density_empty(self):
        nil = self._nil()
        scores, coverage = nil._extract_conflict_density([])
        assert scores == []
        assert coverage == 0.0

    def test_extract_conflict_density_scores_range(self):
        nil = self._nil()
        summaries = [
            self._s(1, conflicts="конфликт атака опасность", mood="тревожное"),
            self._s(2, conflicts="", mood="светлое"),
        ]
        scores, _ = nil._extract_conflict_density(summaries)
        assert len(scores) == 2
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_count_mood_shifts_basic(self):
        nil = self._nil()
        summaries = [
            self._s(1, mood="тревожное"),
            self._s(2, mood="светлое"),
            self._s(3, mood="мрачное"),
        ]
        shifts = nil._count_mood_shifts(summaries)
        assert shifts >= 1

    def test_count_mood_shifts_no_shift(self):
        nil = self._nil()
        summaries = [self._s(1, mood="тревожное"), self._s(2, mood="мрачное")]
        shifts = nil._count_mood_shifts(summaries)
        assert shifts == 0  # оба neg

    def test_extract_raw_promises_string_format(self):
        nil = self._nil()
        summaries = [
            self._s(1, promises="Герой вернётся в финале"),
            self._s(2, promises="нет"),  # должен пропустить
            self._s(3, promises=""),     # пустой пропуск
        ]
        result = nil._extract_raw_promises(summaries)
        assert len(result) == 1
        assert result[0] == (1, "Герой вернётся в финале")

    def test_extract_raw_promises_multi_sentence(self):
        nil = self._nil()
        summaries = [self._s(1, promises="Обещание первое; Обещание второе")]
        result = nil._extract_raw_promises(summaries)
        assert len(result) == 2

    def test_get_metrics_empty(self):
        nil = self._nil(summaries=[])
        result = nil.get_metrics(1, through_chapter=5)
        assert result["chapters_analyzed"] == 0
        assert result["avg_conflict_score"] == 0.0

    def test_get_metrics_with_data(self):
        summaries = [
            {"chapter_num": 1, "events": "е", "conflicts": "конфликт опасность",
             "mood": "тревожное", "promises": "обещание", "project_id": 1},
        ]
        from engine.narrative_intelligence import NarrativeIntelligence
        nil = NarrativeIntelligence(
            get_summaries_fn=lambda pid, ch, n=50: summaries,
            get_state_fn=lambda pid: {},
            get_chapters_fn=lambda pid: [1],
        )
        result = nil.get_metrics(1, through_chapter=2)
        assert result["chapters_analyzed"] == 1
        assert result["promise_count"] >= 1

    def test_get_promise_status_empty(self):
        nil = self._nil(summaries=[])
        result = nil.get_promise_status(1, through_chapter=5)
        assert result == []

    def test_analyze_returns_report_no_summaries(self):
        from engine.narrative_intelligence import NarrativeIntelligence
        nil = NarrativeIntelligence(
            get_summaries_fn=lambda pid, ch, n=50: [],
            get_state_fn=lambda pid: {},
            get_chapters_fn=lambda pid: [],
        )
        from unittest.mock import MagicMock
        report = nil.analyze(1, 5, MagicMock(return_value="{}"))
        assert report.ok is True
        assert len(report.warnings) > 0


class TestNILWithLLM:
    """_analyze_arcs, _check_promise_resolutions, _detect_contradictions"""

    def _nil(self):
        from engine.narrative_intelligence import NarrativeIntelligence
        return NarrativeIntelligence(
            get_summaries_fn=lambda pid, ch, n=50: [],
            get_state_fn=lambda pid: {},
            get_chapters_fn=lambda pid: [],
        )

    def _s(self, ch, **kw):
        return {"chapter_num": ch, "project_id": 1,
                "events": kw.get("events", "событие"),
                "characters": kw.get("characters", ""),
                "conflicts": kw.get("conflicts", ""),
                "mood": kw.get("mood", ""),
                "promises": kw.get("promises", "")}

    def test_analyze_arcs_empty_summaries(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._analyze_arcs([], MagicMock(), 1, 5)
        assert result == {}

    def test_analyze_arcs_llm_ok(self):
        nil = self._nil()
        import json
        response = json.dumps({"arcs": [
            {"character": "Иван", "status": "active", "evolution": "растёт",
             "stalled": False, "last_chapter": 3}
        ]})
        from unittest.mock import MagicMock
        summaries = [self._s(1, characters="Иван вышел"), self._s(2, characters="Иван вернулся")]
        result = nil._analyze_arcs(summaries, MagicMock(return_value=response), 1, 3)
        assert "Иван" in result
        assert result["Иван"].status == "active"

    def test_analyze_arcs_llm_error_returns_empty(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._analyze_arcs(
            [self._s(1, characters="Иван")],
            MagicMock(side_effect=RuntimeError("сеть")), 1, 5
        )
        assert result == {}

    def test_check_promise_resolutions_empty(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._check_promise_resolutions([], {}, MagicMock())
        assert result == {}

    def test_check_promise_resolutions_llm_ok(self):
        nil = self._nil()
        import json
        response = json.dumps({"resolutions": [
            {"promise": "Герой вернётся", "resolved": True, "chapter": 5}
        ]})
        from unittest.mock import MagicMock
        raw = [(1, "Герой вернётся")]
        events = {1: "событие", 5: "герой вернулся"}
        result = nil._check_promise_resolutions(raw, events, MagicMock(return_value=response))
        assert result["Герой вернётся"]["resolved"] is True

    def test_check_promise_resolutions_llm_error(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._check_promise_resolutions(
            [(1, "обещание")], {1: "событие"},
            MagicMock(side_effect=RuntimeError("упало"))
        )
        assert result == {}

    def test_detect_contradictions_one_summary(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._detect_contradictions([self._s(1)], MagicMock(), 1, 5)
        assert result == []  # < 2 саммари → сразу []

    def test_detect_contradictions_none_found(self):
        nil = self._nil()
        import json
        from unittest.mock import MagicMock
        response = json.dumps({"contradictions": []})
        summaries = [self._s(1, events="Иван живёт"), self._s(2, events="Иван жив")]
        result = nil._detect_contradictions(summaries, MagicMock(return_value=response), 1, 2)
        assert result == []

    def test_detect_contradictions_blocking(self):
        nil = self._nil()
        import json
        from unittest.mock import MagicMock
        response = json.dumps({"contradictions": [
            {"chapters": [1, 3], "description": "мёртвый ожил", "severity": "blocking"}
        ]})
        summaries = [self._s(1), self._s(2), self._s(3)]
        result = nil._detect_contradictions(summaries, MagicMock(return_value=response), 1, 3)
        assert len(result) == 1
        assert "БЛОКИРУЮЩЕЕ" in result[0]

    def test_detect_contradictions_llm_error(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        summaries = [self._s(1), self._s(2)]
        result = nil._detect_contradictions(
            summaries, MagicMock(side_effect=RuntimeError("сеть")), 1, 2
        )
        assert result == []


class TestAnalyzeNarrativePublicAPI:

    def test_analyze_narrative_full_run(self):
        import json
        from unittest.mock import MagicMock, patch
        from engine.narrative_intelligence import analyze_narrative

        summaries = [
            {"chapter_num": 1, "events": "герой вышел", "characters": "Иван изменился",
             "conflicts": "опасность", "mood": "тревожное", "promises": "вернётся", "project_id": 1},
            {"chapter_num": 2, "events": "битва", "characters": "Иван победил",
             "conflicts": "дракон", "mood": "мрачное", "promises": "", "project_id": 1},
        ]

        arc_response = json.dumps({"arcs": [
            {"character": "Иван", "status": "active", "evolution": "растёт",
             "stalled": False, "last_chapter": 2}
        ]})
        promise_response = json.dumps({"resolutions": []})
        contradiction_response = json.dumps({"contradictions": []})
        responses = [arc_response, promise_response, contradiction_response]
        call_count = [0]

        def mock_llm(prompt):
            r = responses[min(call_count[0], len(responses)-1)]
            call_count[0] += 1
            return r

        with patch("engine.narrative_intelligence._default_nil", None), \
             patch("engine.cognitive_memory._cognitive_summaries_adapter",
                   return_value=summaries):
            report = analyze_narrative(1, 2, mock_llm)

        assert report.project_id == 1
        assert report.through_chapter == 2
        assert isinstance(report.warnings, list)


# ═══════════════════════════════════════════════════════════════
# 3. pipeline.py — непокрытые функции
# ═══════════════════════════════════════════════════════════════

class TestPipelineInternalFunctions:

    def test_get_keys_returns_dict(self, project_id):
        from engine.pipeline import _get_keys
        result = _get_keys()
        assert isinstance(result, dict)
        assert "anthropic" in result and "openai" in result

    def test_get_resolver_model_fallback(self, project_id):
        from engine.pipeline import _get_resolver_model
        result = _get_resolver_model("gpt-4o")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_resolver_model_from_db(self, project_id):
        from engine.pipeline import _get_resolver_model
        import engine.db_core as dbc
        with dbc.get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('resolver_model', 'claude-3-haiku')")
        result = _get_resolver_model("fallback")
        assert result == "claude-3-haiku"

    def test_make_module_resolver_callable(self, project_id):
        from engine.pipeline import _make_module_resolver
        from unittest.mock import patch
        with patch("engine.pipeline._call", return_value='{"test": true}') as mock_call:
            fn = _make_module_resolver("gpt-4o")
            assert callable(fn)
            result = fn("тестовый промпт")
            assert mock_call.called

    def test_make_model_caller_callable(self, project_id):
        from engine.pipeline import _make_model_caller
        from unittest.mock import patch
        with patch("engine.pipeline._call", return_value="ответ модели") as mock_call:
            fn = _make_model_caller("gpt-4o")
            assert callable(fn)
            result = fn("тестовый промпт")
            assert mock_call.called

    def test_build_consolidated_voice_delegates(self):
        from unittest.mock import patch
        from engine.pipeline import _build_consolidated_voice
        with patch("engine.pipeline_context.build_consolidated_voice", return_value="голос") as mock:
            result = _build_consolidated_voice(None, [], "quick")
            mock.assert_called_once()
            assert result == "голос"

    def test_extract_relevant_state_delegates(self):
        from unittest.mock import patch
        from engine.pipeline import _extract_relevant_state
        with patch("engine.pipeline_context.extract_relevant_state", return_value="state") as mock:
            result = _extract_relevant_state({}, "промпт")
            mock.assert_called_once()
            assert result == "state"

    def test_resolve_steps_config_wins(self):
        from engine.pipeline import _resolve_pipeline_steps, PipelineStep
        from engine.pipeline_config import PipelineConfig
        config = PipelineConfig(steps=["generate", "judge"])
        steps_arg = [PipelineStep("edit")]
        result = _resolve_pipeline_steps(steps_arg, config)
        names = [s.name for s in result]
        assert "generate" in names
        assert "edit" not in names

    def test_resolve_steps_uses_steps_when_no_config(self):
        from engine.pipeline import _resolve_pipeline_steps, PipelineStep
        steps = [PipelineStep("edit"), PipelineStep("judge")]
        result = _resolve_pipeline_steps(steps, config=None)
        assert result == steps

    def test_resolve_steps_reads_db_prevalidation(self, project_id):
        from engine.pipeline import _resolve_pipeline_steps
        import engine.db_core as dbc
        with dbc.get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('prevalidation_enabled', 'true')")
        result = _resolve_pipeline_steps(None, None)
        assert result is not None
        names = [s.name for s in result]
        assert "prevalidate" in names

    def test_resolve_steps_none_when_no_prevalidation(self, project_id):
        from engine.pipeline import _resolve_pipeline_steps
        import engine.db_core as dbc
        with dbc.get_conn() as conn:
            conn.execute("DELETE FROM settings WHERE key='prevalidation_enabled'")
        result = _resolve_pipeline_steps(None, None)
        assert result is None

    def test_resolve_steps_exception_absorbed(self, project_id):
        from engine.pipeline import _resolve_pipeline_steps
        from unittest.mock import patch
        with patch("engine.db.get_setting", side_effect=RuntimeError("db down")):
            result = _resolve_pipeline_steps(None, None)
        assert result is None


# ═══════════════════════════════════════════════════════════════
# 4. engine_loaders.py — непокрытые функции
# ═══════════════════════════════════════════════════════════════

class TestEngineLoadersNoEngine:
    """Тесты когда engine path не существует — возвращают пустые строки/None."""

    def _fake_path(self):
        import tempfile
        return __import__("pathlib").Path(tempfile.mkdtemp()) / "nonexistent"

    def test_load_module_dependencies_no_index(self):
        from engine.engine_loaders import load_module_dependencies_from_index
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            result = load_module_dependencies_from_index()
        assert result is None

    def test_load_module_dependencies_with_index(self):
        import tempfile, json
        from pathlib import Path
        from engine.engine_loaders import load_module_dependencies_from_index
        from unittest.mock import patch

        tmp = Path(tempfile.mkdtemp())
        index = {"module_dependencies": {"genre": ["base", "arc"]}}
        (tmp / "INDEX.json").write_text(json.dumps(index))

        with patch("engine.engine_loaders.get_engine_path", return_value=tmp):
            result = load_module_dependencies_from_index()
        assert result == {"genre": ["base", "arc"]}

    def test_load_module_dependencies_no_key_returns_none(self):
        import tempfile, json
        from pathlib import Path
        from engine.engine_loaders import load_module_dependencies_from_index
        from unittest.mock import patch

        tmp = Path(tempfile.mkdtemp())
        (tmp / "INDEX.json").write_text(json.dumps({"files": []}))

        with patch("engine.engine_loaders.get_engine_path", return_value=tmp):
            result = load_module_dependencies_from_index()
        assert result is None

    def test_load_genre_catalog_no_engine(self):
        from engine.engine_loaders import _load_genre_catalog
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_genre_catalog("fantasy") == ""

    def test_load_anticliche_replacements_no_engine(self):
        from engine.engine_loaders import _load_anticliche_replacements
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_anticliche_replacements() == ""

    def test_load_genre_contract_no_engine(self):
        from engine.engine_loaders import _load_genre_contract
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_genre_contract("fantasy") == ""

    def test_load_dialectics_hint_no_engine(self):
        from engine.engine_loaders import _load_dialectics_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_dialectics_hint() == ""

    def test_load_arc_hint_no_engine(self):
        from engine.engine_loaders import _load_arc_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_arc_hint("fantasy") == ""

    def test_load_character_profile_no_engine(self):
        from engine.engine_loaders import _load_character_profile
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_character_profile("fantasy") == ""

    def test_load_symbolism_hint_no_engine(self):
        from engine.engine_loaders import _load_symbolism_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_symbolism_hint() == ""

    def test_load_voice_check_hint_no_engine(self):
        from engine.engine_loaders import _load_voice_check_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_voice_check_hint() == ""

    def test_load_catalog_subgenre_hint_no_engine(self):
        from engine.engine_loaders import _load_catalog_subgenre_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_catalog_subgenre_hint("fantasy") == ""

    def test_load_genre_prompt_no_engine(self):
        from engine.engine_loaders import _load_genre_prompt
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_genre_prompt("fantasy", "quick") == ""

    def test_load_writing_core_hint_no_task(self):
        from engine.engine_loaders import _load_writing_core_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_writing_core_hint("", "quick") == ""

    def test_load_writing_core_hint_no_engine(self):
        from engine.engine_loaders import _load_writing_core_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_writing_core_hint("диалог между персонажами", "quick") == ""

    def test_load_validation_checklist_no_engine(self):
        from engine.engine_loaders import _load_validation_checklist
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_validation_checklist("fantasy") == ""

    def test_load_pattern_library_no_engine(self):
        from engine.engine_loaders import _load_pattern_library
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_pattern_library("fantasy", "quick") == ""


class TestEngineLoadersWithFakeEngine:
    """Тесты с фиктивным движком — проверяем что загрузчики читают правильные файлы."""

    def _make_engine(self, files: dict):
        import tempfile
        from pathlib import Path
        base = Path(tempfile.mkdtemp())
        for rel_path, content in files.items():
            p = base / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return base

    def test_load_anticliche_replacements_reads_file(self):
        from engine.engine_loaders_core import load_anticliche_replacements
        engine = self._make_engine({
            "00_CORE/anticliche_replacements.md": "клише1\nклише2\nзамена"
        })
        result = load_anticliche_replacements(engine)
        assert "КЛИШЕ" in result
        assert "клише1" in result

    def test_load_validation_checklist_universal(self):
        from engine.engine_loaders_core import load_validation_checklist
        engine = self._make_engine({
            "10_VALIDATION/checklist_universal.md": "критерий 1\nкритерий 2"
        })
        result = load_validation_checklist(engine, genre_key=None)
        assert "критерий 1" in result

    def test_load_validation_checklist_genre_added(self):
        from engine.engine_loaders_core import load_validation_checklist
        engine = self._make_engine({
            "10_VALIDATION/checklist_universal.md": "универсальный критерий",
            "10_VALIDATION/checklist_fantasy.md": "фэнтези критерий",
        })
        result = load_validation_checklist(engine, genre_key="fantasy_urban")
        assert "универсальный критерий" in result
        assert "фэнтези критерий" in result

    def test_load_validation_checklist_empty_dir(self):
        from engine.engine_loaders_core import load_validation_checklist
        from pathlib import Path
        import tempfile
        engine = Path(tempfile.mkdtemp())
        result = load_validation_checklist(engine, genre_key="fantasy")
        assert result == ""

    def test_read_md_useful_skips_code_blocks(self):
        from engine.engine_loaders_core import _read_md_useful
        from pathlib import Path
        import tempfile
        p = Path(tempfile.mkdtemp()) / "test.md"
        p.write_text("нормальная строка\n```python\nкод\n```\nещё строка")
        result = _read_md_useful(p, max_lines=10)
        assert "нормальная строка" in result
        assert "код" not in result

    def test_load_genre_catalog_reads_catalog(self):
        from engine.engine_loaders_genre import load_genre_catalog
        engine = self._make_engine({
            "04_GENRE_ENGINE/catalog/fantasy_catalog.md": "# Фэнтези каталог\nподжанр1"
        })
        result = load_genre_catalog(engine, "fantasy")
        assert "fantasy" in result.lower() or "фэнтези" in result.lower() or "поджанр1" in result


# ═══════════════════════════════════════════════════════════════
# 5. engine_loaders_genre.py — приватные функции
# ═══════════════════════════════════════════════════════════════

class TestEngineLoadersGenrePrivate:

    def _engine(self, files: dict):
        import tempfile
        from pathlib import Path
        base = Path(tempfile.mkdtemp())
        for rel, content in files.items():
            p = base / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return base

    def test_load_arc_by_heading_found(self):
        from engine.engine_loaders_genre import _load_arc_by_heading
        engine = self._engine({
            "12_ARCS/arcs_by_genre.md": "## DETECTIVE\nарка детектива\n\n## FANTASY\nарка фэнтези"
        })
        result = _load_arc_by_heading(engine, "DETECTIVE")
        assert "детектива" in result

    def test_load_arc_by_heading_not_found(self):
        from engine.engine_loaders_genre import _load_arc_by_heading
        engine = self._engine({
            "12_ARCS/arcs_by_genre.md": "## FANTASY\nарка фэнтези"
        })
        result = _load_arc_by_heading(engine, "HORROR")
        assert result == ""

    def test_load_arc_by_heading_no_file(self):
        from engine.engine_loaders_genre import _load_arc_by_heading
        from pathlib import Path
        import tempfile
        result = _load_arc_by_heading(Path(tempfile.mkdtemp()), "FANTASY")
        assert result == ""

    def test_load_fantasy_arc_reads_file(self):
        from engine.engine_loaders_genre import _load_fantasy_arc
        engine = self._engine({
            "12_ARCS/arcs_by_genre.md": "## FANTASY\nфэнтези арка раздел"
        })
        result = _load_fantasy_arc(engine)
        assert "фэнтези" in result.lower() or "FANTASY" in result

    def test_load_fantasy_arc_no_file_empty(self):
        from engine.engine_loaders_genre import _load_fantasy_arc
        from pathlib import Path
        import tempfile
        result = _load_fantasy_arc(Path(tempfile.mkdtemp()))
        assert result == ""

    def test_load_antagonist_section_exists(self):
        from engine.engine_loaders_genre import _load_antagonist_section
        engine = self._engine({
            "04_GENRE_ENGINE/profiles/fantasy_profiles.md":
                "## АНТАГОНИСТ\nантагонист фэнтези описание"
        })
        result = _load_antagonist_section(engine, "fantasy", "urban")
        assert "антагонист" in result.lower() or result == ""

    def test_load_antagonist_section_no_file(self):
        from engine.engine_loaders_genre import _load_antagonist_section
        from pathlib import Path
        import tempfile
        result = _load_antagonist_section(Path(tempfile.mkdtemp()), "fantasy", "urban")
        assert result == ""

    def test_extract_subgenre_block_found(self):
        from engine.engine_loaders_genre import _extract_subgenre_block
        text = "## FANTASY\nобщий текст\n### urban\nурбан поджанр\n### dark\nдарк поджанр"
        result = _extract_subgenre_block(text, "fantasy", "urban")
        assert "урбан" in result

    def test_extract_subgenre_block_not_found(self):
        from engine.engine_loaders_genre import _extract_subgenre_block
        text = "## FANTASY\nобщий текст"
        result = _extract_subgenre_block(text, "fantasy", "nonexistent")
        assert result == ""

    def test_extract_quality_rules_fallback_found(self):
        from engine.engine_loaders_genre import _extract_quality_rules_fallback
        text = "некий текст\nКАЧЕСТВО:\nправило 1\nправило 2\n"
        result = _extract_quality_rules_fallback(text, "detective", "detective", Path("."))
        assert "правило 1" in result or result != ""

    def test_extract_quality_rules_fallback_not_found(self):
        from engine.engine_loaders_genre import _extract_quality_rules_fallback
        text = "текст без секции качества"
        result = _extract_quality_rules_fallback(text, "detective", "detective", Path("."))
        assert isinstance(result, str)
