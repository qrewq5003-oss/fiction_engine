"""
test_cognitive_memory.py — тесты когнитивной памяти.

Критические инварианты:
  1. promises не затухают (decay_rate=0.00)
  2. recent_chapters всегда включаются (последние 2)
  3. mood затухает быстрее events
  4. get_weighted_promises возвращает строку с активными промисами
  5. get_cognitive_context возвращает строку даже без саммари

ВАЖНО: патчим engine.cognitive_memory.get_l3_summaries (не _get_summaries —
такой функции нет). get_weighted_promises возвращает str, не list[tuple].
"""

import pytest
from unittest.mock import patch, MagicMock


# ─── Константы весов из модуля ────────────────────────────────────────────────

def get_memory_fields():
    from engine.cognitive_memory import MEMORY_FIELDS
    return {f.key: f for f in MEMORY_FIELDS}


# ─── Тест 1: веса и затухание ─────────────────────────────────────────────────

def test_promises_no_decay():
    """promises.decay_rate должен быть 0 — они не затухают."""
    fields = get_memory_fields()
    assert "promises" in fields
    assert fields["promises"].decay_rate == 0.0, (
        f"promises.decay_rate={fields['promises'].decay_rate}, ожидалось 0.0"
    )

def test_promises_highest_base_weight():
    """promises имеет наивысший base_weight среди всех полей."""
    fields = get_memory_fields()
    max_weight = max(f.base_weight for f in fields.values())
    assert fields["promises"].base_weight == max_weight, (
        f"promises.base_weight={fields['promises'].base_weight}, "
        f"максимальный вес={max_weight}"
    )

def test_mood_decays_faster_than_events():
    """mood затухает быстрее events (более высокий decay_rate)."""
    fields = get_memory_fields()
    assert fields["mood"].decay_rate > fields["events"].decay_rate, (
        f"mood.decay_rate={fields['mood'].decay_rate} должен быть > "
        f"events.decay_rate={fields['events'].decay_rate}"
    )

def test_mood_decays_faster_than_conflicts():
    """mood затухает быстрее conflicts."""
    fields = get_memory_fields()
    assert fields["mood"].decay_rate > fields["conflicts"].decay_rate


# ─── Вспомогательная функция ──────────────────────────────────────────────────

def _make_summaries(data: list[dict]) -> list[dict]:
    """Создать список саммари в формате когнитивной памяти."""
    return [
        {
            "chapter_num": item["chapter"],
            "promises":    item.get("promises", []),
            "conflicts":   item.get("conflicts", ""),
            "characters":  item.get("characters", ""),
            "events":      item.get("events", ""),
            "mood":        item.get("mood", ""),
        }
        for item in data
    ]


def _active_promise(chapter: int, idx: int, text: str) -> dict:
    """Создать активный promise-объект."""
    return {"id": f"{chapter}_{idx}", "text": text, "resolved": False, "resolved_chapter": None}


# ─── Тест 2: get_weighted_promises ───────────────────────────────────────────

def test_weighted_promises_collects_all():
    """get_weighted_promises включает активные промисы из всех глав, не только последних."""
    from engine.cognitive_memory import get_weighted_promises

    summaries = _make_summaries([
        {"chapter": 1, "promises": [_active_promise(1, 0, "Убийца вернётся")]},
        {"chapter": 2, "promises": []},
        {"chapter": 5, "promises": [_active_promise(5, 0, "Ключ спрятан в доме")]},
        {"chapter": 9, "promises": [_active_promise(9, 0, "Предательство откроется")]},
    ])

    with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_weighted_promises(project_id=1, before_chapter=10, n=50)

    assert isinstance(result, str), "get_weighted_promises должен возвращать строку"
    assert "Убийца" in result,        "промис из гл.1 должен быть включён"
    assert "Ключ спрятан" in result,  "промис из гл.5 должен быть включён"
    assert "Предательство" in result, "промис из гл.9 должен быть включён"

def test_weighted_promises_skips_empty():
    """get_weighted_promises не включает главы без активных промисов."""
    from engine.cognitive_memory import get_weighted_promises

    summaries = _make_summaries([
        {"chapter": 1, "promises": []},
        {"chapter": 2, "promises": []},
        {"chapter": 3, "promises": [_active_promise(3, 0, "Настоящий промис")]},
    ])

    with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_weighted_promises(project_id=1, before_chapter=4, n=50)

    assert "Настоящий промис" in result
    assert result.count("Гл.") == 1, "только одна глава должна присутствовать"

def test_weighted_promises_returns_empty_string_when_no_summaries():
    """Пустой список саммари → пустая строка."""
    from engine.cognitive_memory import get_weighted_promises

    with patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
        result = get_weighted_promises(project_id=1, before_chapter=5)

    assert result == ""

def test_weighted_promises_excludes_resolved():
    """Закрытые промисы не попадают в вывод."""
    from engine.cognitive_memory import get_weighted_promises

    summaries = _make_summaries([
        {"chapter": 1, "promises": [
            {"id": "1_0", "text": "Активное",  "resolved": False},
            {"id": "1_1", "text": "Закрытое",  "resolved": True, "resolved_chapter": 3},
        ]},
    ])

    with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_weighted_promises(project_id=1, before_chapter=5)

    assert "Активное" in result
    assert "Закрытое" not in result


# ─── Тест 3: get_cognitive_context ───────────────────────────────────────────

def test_cognitive_context_empty_summaries():
    """get_cognitive_context возвращает строку даже если нет саммари."""
    from engine.cognitive_memory import get_cognitive_context

    with patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
        result = get_cognitive_context(project_id=1, before_chapter=5)

    assert isinstance(result, str)

def test_cognitive_context_includes_recent():
    """Последние 2 главы всегда включаются в контекст."""
    from engine.cognitive_memory import get_cognitive_context

    summaries = _make_summaries([
        {"chapter": 1, "events": "старое событие", "mood": "нейтральное"},
        {"chapter": 2, "events": "событие 2",      "mood": "тревожное"},
        {"chapter": 3, "events": "событие 3",      "mood": "мрачное"},
    ])

    with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_cognitive_context(project_id=1, before_chapter=4)

    assert "событие 2" in result or "событие 3" in result, (
        "последние главы должны быть в когнитивном контексте"
    )

def test_cognitive_context_includes_promises_from_all():
    """Активные промисы из ранних глав должны быть в контексте."""
    from engine.cognitive_memory import get_cognitive_context

    summaries = _make_summaries([
        {"chapter": 1, "promises": [_active_promise(1, 0, "Убийца вернётся")], "mood": "тёмное"},
        {"chapter": 2, "mood": "нейтральное"},
        {"chapter": 3, "mood": "нейтральное"},
        {"chapter": 4, "mood": "нейтральное"},
        {"chapter": 5, "mood": "нейтральное"},
    ])

    with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_cognitive_context(project_id=1, before_chapter=6)

    assert "Убийца" in result, (
        "промис из гл.1 должен быть в контексте даже для гл.6 (promises не затухают)"
    )

def test_cognitive_context_excludes_resolved_promises():
    """Закрытые промисы не попадают в когнитивный контекст."""
    from engine.cognitive_memory import get_cognitive_context

    summaries = _make_summaries([
        {"chapter": 1, "promises": [
            {"id": "1_0", "text": "Закрытое обещание", "resolved": True, "resolved_chapter": 2},
        ]},
        {"chapter": 2, "events": "событие"},
    ])

    with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_cognitive_context(project_id=1, before_chapter=5)

    assert "Закрытое обещание" not in result


# ─── Тест 4: MemoryField ─────────────────────────────────────────────────────

def test_memory_field_floor_is_positive():
    """Все поля имеют floor > 0 — минимальный вес не нулевой."""
    fields = get_memory_fields()
    for key, field in fields.items():
        assert field.floor > 0, f"{key}.floor должен быть > 0"

def test_memory_field_required_keys_exist():
    """Все обязательные поля присутствуют."""
    fields = get_memory_fields()
    required = {"promises", "conflicts", "characters", "events", "mood"}
    missing = required - set(fields.keys())
    assert not missing, f"Отсутствуют поля: {missing}"
