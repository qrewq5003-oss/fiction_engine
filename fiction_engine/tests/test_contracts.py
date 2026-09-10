"""
test_contracts.py — engine/contracts.py

contracts.py содержит только Protocol-интерфейсы.
Тестируем:
A. Все классы импортируются без ошибок
B. @runtime_checkable Protocol проверяет конкретные объекты
C. NarrativeReport и dataclass-подобные классы конструируются
"""
import pytest


class TestProtocolImports:
    def test_all_protocols_importable(self):
        from engine.contracts import (
            LLMCaller, FullModelCaller, SummaryStore, ChapterStore,
            StateStore, PipelineStage, NarrativeAnalyzer,
            NarrativeReport, ArcStatus, PromiseItem,
        )

    def test_llm_caller_protocol_runtime_checkable(self):
        from engine.contracts import LLMCaller
        # Lambda с одним аргументом удовлетворяет LLMCaller
        fn = lambda prompt: "response"
        assert isinstance(fn, LLMCaller)

    def test_non_callable_not_llm_caller(self):
        from engine.contracts import LLMCaller
        assert not isinstance(42, LLMCaller)
        assert not isinstance("string", LLMCaller)


class TestNarrativeReport:
    def test_constructible_with_defaults(self):
        from engine.contracts import NarrativeReport
        report = NarrativeReport(project_id=1, through_chapter=5)
        assert hasattr(report, "ok")
        assert hasattr(report, "warnings")
        assert hasattr(report, "arc_health")

    def test_ok_default_true(self):
        from engine.contracts import NarrativeReport
        report = NarrativeReport(project_id=1, through_chapter=5)
        assert report.ok is True

    def test_warnings_default_empty(self):
        from engine.contracts import NarrativeReport
        report = NarrativeReport(project_id=1, through_chapter=5)
        assert report.warnings == []

    def test_custom_values(self):
        from engine.contracts import NarrativeReport
        report = NarrativeReport(project_id=1, through_chapter=5,
                                 ok=False, warnings=["проблема"])
        assert report.ok is False
        assert "проблема" in report.warnings


class TestArcStatus:
    def test_constructible(self):
        from engine.contracts import ArcStatus
        # поля: character / status / last_seen_chapter (см. __slots__)
        arc = ArcStatus(character="Арка1", status="active", last_seen_chapter=1)
        assert arc.character == "Арка1"
        assert arc.status == "active"


class TestPromiseItem:
    def test_constructible(self):
        from engine.contracts import PromiseItem
        # поле называется introduced_chapter, а не chapter
        p = PromiseItem(text="Герой вернётся", introduced_chapter=1, resolved=False)
        assert p.introduced_chapter == 1
        assert p.resolved is False
