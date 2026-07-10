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
        report = NarrativeReport()
        assert hasattr(report, "ok")
        assert hasattr(report, "warnings")
        assert hasattr(report, "arcs")

    def test_ok_default_true(self):
        from engine.contracts import NarrativeReport
        report = NarrativeReport()
        assert report.ok is True

    def test_warnings_default_empty(self):
        from engine.contracts import NarrativeReport
        report = NarrativeReport()
        assert report.warnings == []

    def test_custom_values(self):
        from engine.contracts import NarrativeReport
        report = NarrativeReport(ok=False, warnings=["проблема"])
        assert report.ok is False
        assert "проблема" in report.warnings


class TestArcStatus:
    def test_constructible(self):
        from engine.contracts import ArcStatus
        arc = ArcStatus(name="Арка1", status="active", introduced_chapter=1)
        assert arc.name == "Арка1"
        assert arc.status == "active"


class TestPromiseItem:
    def test_constructible(self):
        from engine.contracts import PromiseItem
        p = PromiseItem(chapter=1, text="Герой вернётся", resolved=False)
        assert p.chapter == 1
        assert p.resolved is False
