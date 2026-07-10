"""
test_error_policy.py — тесты error_policy.py

Проверяем поведение всех трёх уровней: RECOVERABLE, DEGRADED, FATAL.
"""

import pytest
from engine.error_policy import (
    error_boundary, handle_error, ErrorLevel, ErrorPolicy, PipelineError
)


class TestErrorLevel:
    def test_recoverable_returns_fallback(self):
        @error_boundary(level=ErrorLevel.RECOVERABLE, fallback="default")
        def broken():
            raise ValueError("что-то сломалось")

        assert broken() == "default"

    def test_degraded_returns_fallback(self):
        @error_boundary(level=ErrorLevel.DEGRADED, fallback=[])
        def broken():
            raise RuntimeError("сервис недоступен")

        assert broken() == []

    def test_fatal_raises_pipeline_error(self):
        @error_boundary(level=ErrorLevel.FATAL)
        def broken():
            raise ConnectionError("нет сети")

        with pytest.raises(PipelineError) as exc_info:
            broken()
        assert "broken" in str(exc_info.value)

    def test_fatal_wraps_original_exception(self):
        original = ValueError("оригинальная ошибка")

        @error_boundary(level=ErrorLevel.FATAL)
        def broken():
            raise original

        with pytest.raises(PipelineError) as exc_info:
            broken()
        assert exc_info.value.original is original

    def test_no_error_returns_result(self):
        @error_boundary(level=ErrorLevel.RECOVERABLE, fallback="fallback")
        def works():
            return "результат"

        assert works() == "результат"

    def test_fatal_not_caught_by_recoverable(self):
        """PipelineError пробрасывается сквозь RECOVERABLE декоратор."""
        @error_boundary(level=ErrorLevel.RECOVERABLE, fallback="inner_fallback")
        def inner():
            raise PipelineError("контекст", ValueError("причина"))

        # PipelineError не должен быть поглощён RECOVERABLE
        with pytest.raises(PipelineError):
            inner()

    def test_fallback_none_by_default(self):
        @error_boundary(level=ErrorLevel.RECOVERABLE)
        def broken():
            raise Exception("упало")

        assert broken() is None

    def test_custom_context_in_log(self, capsys):
        @error_boundary(level=ErrorLevel.RECOVERABLE, fallback=0, context="мой_контекст")
        def broken():
            raise ValueError("тест")

        broken()  # не должно упасть


class TestHandleError:
    def test_recoverable_returns_fallback(self):
        result = handle_error("ctx", ValueError("err"),
                               level=ErrorLevel.RECOVERABLE, fallback=42)
        assert result == 42

    def test_degraded_returns_fallback(self):
        result = handle_error("ctx", RuntimeError("err"),
                               level=ErrorLevel.DEGRADED, fallback={})
        assert result == {}

    def test_fatal_raises(self):
        with pytest.raises(PipelineError):
            handle_error("ctx", Exception("err"), level=ErrorLevel.FATAL)


class TestErrorPolicy:
    def test_for_step_generate_is_fatal(self):
        policy = ErrorPolicy.for_step("generate")
        assert policy.level == ErrorLevel.FATAL

    def test_for_step_critique_is_degraded(self):
        policy = ErrorPolicy.for_step("critique")
        assert policy.level == ErrorLevel.DEGRADED

    def test_for_step_memory_is_recoverable(self):
        policy = ErrorPolicy.for_step("memory")
        assert policy.level == ErrorLevel.RECOVERABLE

    def test_for_step_unknown_is_recoverable(self):
        policy = ErrorPolicy.for_step("несуществующий_шаг")
        assert policy.level == ErrorLevel.RECOVERABLE

    def test_policy_handle_fatal_raises(self):
        policy = ErrorPolicy(ErrorLevel.FATAL)
        with pytest.raises(PipelineError):
            policy.handle("тест", ValueError("ошибка"))

    def test_policy_handle_recoverable_returns_fallback(self):
        policy = ErrorPolicy(ErrorLevel.RECOVERABLE)
        result = policy.handle("тест", ValueError("ошибка"), fallback="fb")
        assert result == "fb"


class TestPipelineError:
    def test_str_representation(self):
        err = PipelineError("генерация главы", RuntimeError("timeout"))
        assert "FATAL" in str(err)
        assert "генерация главы" in str(err)

    def test_original_exception_preserved(self):
        original = ConnectionError("сервер упал")
        err = PipelineError("ctx", original)
        assert err.original is original

    def test_context_preserved(self):
        err = PipelineError("мой_контекст", ValueError("x"))
        assert err.context == "мой_контекст"
