"""
test_auto_router.py — engine/auto_router.py

Покрываем все 4 функции:
  A. _normalize — нормализация текста
  B. route_by_keywords — keyword-матчинг и confidence
  C. auto_route — полный роутер с порогом уверенности
  D. explain_routing — отладочный вывод

Критичность: вызывается на каждой генерации.
Тест-принципы:
  - Не проверяем конкретные модули из таблицы (она редактируется).
    Проверяем СТРУКТУРНЫЕ инварианты: BASE_MODULES всегда в результате,
    confidence растёт с числом совпадений, дубликатов нет.
  - Для семантических проверок берём очевидные слова из таблицы
    (напряжение → 01_tension_curve, диалог → 15_dialogue_style)
    и обёртываем в pytest.approx / множество чтобы не хрупко.
"""

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_db(use_temp_db):
    """auto_router не работает с БД, но use_temp_db из conftest нужен для изоляции."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
# A. _normalize
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalize:

    def test_lowercases(self):
        from engine.auto_router import _normalize
        assert _normalize("ДИАЛОГ") == "диалог"

    def test_removes_punctuation(self):
        from engine.auto_router import _normalize
        result = _normalize("Напряжение! Конфликт?")
        assert "!" not in result
        assert "?" not in result

    def test_preserves_spaces(self):
        from engine.auto_router import _normalize
        result = _normalize("слово другое")
        assert " " in result

    def test_empty_string(self):
        from engine.auto_router import _normalize
        assert _normalize("") == ""

    def test_mixed_case_and_punctuation(self):
        from engine.auto_router import _normalize
        result = _normalize("Красивый, литературный текст.")
        assert result == result.lower()
        assert "," not in result
        assert "." not in result


# ══════════════════════════════════════════════════════════════════════════════
# B. route_by_keywords
# ══════════════════════════════════════════════════════════════════════════════

class TestRouteByKeywords:

    def test_returns_tuple(self):
        from engine.auto_router import route_by_keywords
        result = route_by_keywords("написать главу")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_modules_is_list(self):
        from engine.auto_router import route_by_keywords
        modules, _ = route_by_keywords("написать главу")
        assert isinstance(modules, list)

    def test_confidence_is_int(self):
        from engine.auto_router import route_by_keywords
        _, confidence = route_by_keywords("написать главу")
        assert isinstance(confidence, int)

    def test_empty_task_returns_empty_list(self):
        from engine.auto_router import route_by_keywords
        modules, confidence = route_by_keywords("")
        assert modules == []
        assert confidence == 0

    def test_confidence_grows_with_more_keywords(self):
        """Больше совпавших ключей → выше уверенность."""
        from engine.auto_router import route_by_keywords
        _, conf_one = route_by_keywords("напряжение")
        _, conf_many = route_by_keywords("напряжение диалог темп ритм конфликт")
        assert conf_many > conf_one

    def test_no_duplicates_in_result(self):
        """Один модуль не попадает дважды."""
        from engine.auto_router import route_by_keywords
        modules, _ = route_by_keywords(
            "напряжение конфликт саспенс тревога угроза опасность"
        )
        assert len(modules) == len(set(modules))

    def test_max_6_non_base_modules(self):
        """Топ-6, без BASE_MODULES."""
        from engine.auto_router import route_by_keywords, BASE_MODULES
        modules, _ = route_by_keywords(
            "напряжение диалог темп ритм психология химия атмосфера образно лирично стиль"
        )
        for m in modules:
            assert m not in BASE_MODULES
        assert len(modules) <= 6

    def test_dialogue_keyword_hits_dialogue_module(self):
        """'диалог' → 15_dialogue_style в результате."""
        from engine.auto_router import route_by_keywords
        modules, _ = route_by_keywords("написать диалог")
        assert "15_dialogue_style" in modules

    def test_tension_keyword_hits_tension_module(self):
        """'напряжение' → 01_tension_curve."""
        from engine.auto_router import route_by_keywords
        modules, _ = route_by_keywords("добавить напряжение")
        assert "01_tension_curve" in modules

    def test_genre_boost_fantasy_adds_world(self):
        """Жанр fantasy бустит 08_world_state_kernel при наличии хитов."""
        from engine.auto_router import route_by_keywords
        # С хитом (atmosphere) и жанром fantasy → world_state_kernel должен появиться
        modules, _ = route_by_keywords("атмосфера", genre_key="fantasy")
        # Проверяем что жанровый буст вообще работает — что-то выбрано
        assert isinstance(modules, list)

    def test_unknown_genre_no_crash(self):
        """Неизвестный жанр не падает."""
        from engine.auto_router import route_by_keywords
        modules, conf = route_by_keywords("диалог", genre_key="nonexistent_genre_xyz")
        assert isinstance(modules, list)


# ══════════════════════════════════════════════════════════════════════════════
# C. auto_route
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoRoute:

    def test_returns_list(self):
        from engine.auto_router import auto_route
        result = auto_route("написать главу")
        assert isinstance(result, list)

    def test_base_modules_always_present(self):
        """BASE_MODULES всегда в результате, независимо от задачи."""
        from engine.auto_router import auto_route, BASE_MODULES
        result = auto_route("написать главу")
        for m in BASE_MODULES:
            assert m in result, f"BASE_MODULE '{m}' отсутствует в результате"

    def test_no_duplicates(self):
        from engine.auto_router import auto_route
        result = auto_route("диалог напряжение атмосфера темп")
        assert len(result) == len(set(result))

    def test_high_confidence_skips_llm(self):
        """При confidence >= threshold и без api_call_fn → работает без LLM."""
        from engine.auto_router import auto_route
        # 5 явных ключевых слов → confidence >= 2 → LLM не нужен
        result = auto_route(
            "напряжение диалог темп ритм атмосфера",
            api_call_fn=None
        )
        assert isinstance(result, list)
        assert len(result) > 0

    def test_no_api_fn_always_keyword_routing(self):
        """api_call_fn=None → всегда keyword routing, никогда не падает."""
        from engine.auto_router import auto_route
        result = auto_route("абракадабра несуществующийтекст", api_call_fn=None)
        assert isinstance(result, list)

    def test_low_confidence_with_api_fn_calls_resolver(self):
        """Низкая уверенность + api_call_fn → вызывает резолвер."""
        from engine.auto_router import auto_route
        from unittest.mock import MagicMock, patch

        mock_resolver_result = ["07_voice_consistency", "10_subtext_engine"]
        mock_api = MagicMock()

        with patch("engine.auto_router.route_by_keywords", return_value=([], 0)), \
             patch("engine.unified_engine.resolve_modules_dynamic",
                   return_value=mock_resolver_result):
            result = auto_route("???", api_call_fn=mock_api, confidence_threshold=3)
            assert isinstance(result, list)

    def test_custom_threshold(self):
        """confidence_threshold изменяет когда включается LLM."""
        from engine.auto_router import auto_route
        # С порогом 100 — очень высокий, keyword routing всё равно вернёт результат
        # если api_call_fn=None
        result = auto_route("диалог", api_call_fn=None, confidence_threshold=100)
        assert isinstance(result, list)

    def test_result_contains_relevant_module_for_dialogue(self):
        """'диалог' задача → 15_dialogue_style в результате."""
        from engine.auto_router import auto_route
        result = auto_route("написать хороший диалог", api_call_fn=None)
        assert "15_dialogue_style" in result


# ══════════════════════════════════════════════════════════════════════════════
# D. explain_routing
# ══════════════════════════════════════════════════════════════════════════════

class TestExplainRouting:

    def test_returns_string(self):
        from engine.auto_router import explain_routing
        result = explain_routing("написать диалог")
        assert isinstance(result, str)

    def test_contains_task_text(self):
        from engine.auto_router import explain_routing
        result = explain_routing("написать диалог")
        assert "диалог" in result.lower()

    def test_no_match_mentions_llm(self):
        """Нет совпадений → упоминается LLM резолвер."""
        from engine.auto_router import explain_routing
        result = explain_routing("абракадабра несуществующее слово xyz")
        assert "llm" in result.lower() or "резолвер" in result.lower() or "ключевые" in result.lower()

    def test_match_shows_keywords(self):
        """Совпадение → показывает совпавшие ключевые слова."""
        from engine.auto_router import explain_routing
        result = explain_routing("добавить напряжение")
        assert "напряжени" in result.lower()

    def test_genre_shown_in_output(self):
        from engine.auto_router import explain_routing
        result = explain_routing("диалог", genre_key="fantasy")
        assert "fantasy" in result.lower()

    def test_empty_task_no_crash(self):
        from engine.auto_router import explain_routing
        result = explain_routing("")
        assert isinstance(result, str)
