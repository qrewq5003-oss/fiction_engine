#!/usr/bin/env python3
"""
Манифест базы UNIFIED_ENGINE_MASTER совпадает с тем, что читает код.

Зачем. Из 233 файлов базы код читал 126, а INDEX.json и проверка при
старте этого не отражали: «критическими» числились CORE_FULL, CORE_MINI и
META_RULES, которые не открывал ни один загрузчик, total_files отставал
от диска на 7, README описывал 10 папок из 17 и версию 1.0 при INDEX 1.8
(AUDIT_UNIFIED.md, U4, улучшение 6).

Теперь INDEX.json → runtime_files перечисляет файлы, которые читает
движок, — остальные справочник. Тест трассирует чтение по всем путям
загрузчиков и требует точного совпадения в обе стороны. Изменился набор —
обновите манифест:

    python tests/unified_trace.py
"""

import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, str(Path(__file__).parent))
from unified_trace import files_on_disk, traced_runtime_files  # noqa: E402

KB = Path(__file__).resolve().parents[2] / "UNIFIED_ENGINE_MASTER"
FIX = "обновите манифест: python tests/unified_trace.py"


@pytest.fixture(scope="module")
def index() -> dict:
    assert KB.is_dir(), f"UNIFIED_ENGINE_MASTER не найден: {KB}"
    return json.loads((KB / "INDEX.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def traced() -> set[str]:
    return traced_runtime_files(KB)


def test_runtime_files_match_what_code_reads(index, traced):
    listed = set(index.get("runtime_files", []))
    assert not traced - listed, f"код читает файлы не из манифеста: {sorted(traced - listed)}; {FIX}"
    assert not listed - traced, f"манифест называет нечитаемые файлы: {sorted(listed - traced)}; {FIX}"


def test_files_and_total_match_disk(index):
    disk = files_on_disk(KB)
    assert index["files"] == disk, FIX
    assert index["total_files"] == sum(len(v) for v in disk.values()), FIX


def test_readme_version_and_counts_match_index(index):
    readme = (KB / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^# UNIFIED ENGINE MASTER v(\S+)", readme, re.M)
    assert m and m.group(1) == index["version"], "версия в README расходится с INDEX.json"
    counts = re.search(r"\((\d+) файл\w* из (\d+)\)", readme)
    assert counts, "README не называет число читаемых файлов"
    assert (int(counts.group(1)), int(counts.group(2))) == \
        (len(index["runtime_files"]), index["total_files"]), "числа в README устарели"


def test_startup_check_paths_are_runtime(index):
    """Проверка при старте смотрит только на то, что движок действительно читает."""
    from engine.engine_loaders import _CRITICAL_PATHS, _OPTIONAL_PATHS
    runtime = index["runtime_files"]
    for path in _CRITICAL_PATHS + _OPTIONAL_PATHS:
        used = path in runtime or any(f.startswith(path + "/") for f in runtime)
        assert used, f"{path} проверяется при старте, но движок его не читает"


def test_no_marketing_marks():
    """«Рейтинг 5++/5» и «PRODUCTION READY» — оценки самим себе, а не содержание."""
    marks = re.compile(r"5\+*/5|PRODUCTION READY")
    hits = [f"{p.relative_to(KB)}:{i}"
            for p in sorted(KB.rglob("*.md"))
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if marks.search(line)]
    assert not hits, hits


def test_working_folders_hold_only_runtime_files(index):
    """
    Справочник — в _reference/, устаревшее — в _archive/. В рабочих папках
    только то, что читает движок, и README: иначе по раскладке не видно,
    какой файл меняет промпт, а какой нет.
    """
    runtime = set(index["runtime_files"])
    stray = sorted(
        p.relative_to(KB).as_posix() for p in KB.rglob("*")
        if p.is_file()
        and p.relative_to(KB).parts[0] not in ("_reference", "_archive")
        and p.name not in ("README.md", "INDEX.json")
        and p.relative_to(KB).as_posix() not in runtime
    )
    assert not stray, f"не читаются движком — перенесите в _reference/: {stray}"
