#!/usr/bin/env python3
"""
Код совместим с Python 3.10 — как обещает pyproject.toml (requires-python).

Зачем. f-строка с кавычками того же типа внутри выражения —
f"{d["key"]}" — законна только с Python 3.12 (PEP 701). Локально стоит
3.13, и такой код работает; CI идёт на 3.11, и там модуль не
импортируется: три тестовых файла не собирались, CI был красным с
сентября. Здесь это ловится на любой версии: токенизатор 3.12+ видит
вложенную строку с той же кавычкой, что у внешней f-строки.
"""

import io
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [p for d in ("engine", "web", "tests") for p in (ROOT / d).rglob("*.py")] \
          + [ROOT / "cli.py"]


def _quote(token_string: str) -> str:
    body = token_string.lstrip("rRbBfFuU")
    return body[:3] if body[:3] in ('"""', "'''") else body[:1]


def reused_quotes(src: str) -> list[int]:
    """Строки, где внутри f-строки стоит строка с той же кавычкой, что снаружи."""
    fstart = getattr(tokenize, "FSTRING_START", None)
    fend = getattr(tokenize, "FSTRING_END", None)
    stack: list[str] = []
    bad = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.STRING, fstart) and stack:
            if _quote(tok.string) in stack:
                bad.append(tok.start[0])
        if tok.type == fstart:
            stack.append(_quote(tok.string))
        elif tok.type == fend and stack:
            stack.pop()
    return bad


@pytest.mark.skipif(sys.version_info < (3, 12),
                    reason="до 3.12 такой код просто не импортируется — это ловит сбор тестов")
def test_no_pep701_fstrings():
    hits = [f"{p.relative_to(ROOT)}:{line}"
            for p in SOURCES for line in reused_quotes(p.read_text(encoding="utf-8"))]
    assert not hits, f"f-строка с той же кавычкой внутри (нужен Python 3.12+): {hits}"


def test_detector_catches_example():
    if sys.version_info < (3, 12):
        pytest.skip("токенизатор до 3.12 не разбирает f-строки на части")
    assert reused_quotes('x = f"{d["k"]}"\n') == [1]
    assert reused_quotes("x = f\"{d['k']}\"\n") == []
