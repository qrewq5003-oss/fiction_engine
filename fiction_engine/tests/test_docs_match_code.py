#!/usr/bin/env python3
"""
test_docs_match_code.py — документация не должна расходиться с кодом.

Зачем. README движка описывал `engine/` как три файла (api, db, state),
тогда как модулей там 36: он отстал примерно на две крупные итерации и
скорее вводил в заблуждение, чем помогал. Отставание никто не замечал,
потому что документацию ничто не проверяло.

Здесь проверяется ровно это: каждый модуль, команда CLI и страница
названы в README, и наоборот — README не ссылается на то, чего нет.
"""

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

APP_ROOT  = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent

APP_README  = (APP_ROOT / "README.md").read_text(encoding="utf-8")
ROOT_README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _engine_modules() -> set[str]:
    return {p.stem for p in (APP_ROOT / "engine").glob("*.py")
            if p.stem != "__init__"}


# ─── Модули ───────────────────────────────────────────────────────────────────

def test_every_engine_module_is_documented():
    """Новый модуль обязан появиться в README движка."""
    undocumented = sorted(m for m in _engine_modules()
                          if f"{m}.py" not in APP_README)
    assert not undocumented, (
        "модули есть в engine/, но не описаны в fiction_engine/README.md: "
        + ", ".join(undocumented)
    )


def test_readme_mentions_only_existing_modules():
    """README не должен ссылаться на удалённые модули."""
    mentioned = set(re.findall(r"`(\w+)\.py`", APP_README))
    known = _engine_modules() | {
        "cli", "check_architecture", "app",
        "sigcheck", "pitfalls", "dead",
    }
    ghosts = sorted(mentioned - known)
    assert not ghosts, (
        "README упоминает несуществующие файлы: " + ", ".join(ghosts)
    )


def test_module_count_in_readme_is_accurate():
    """Если в README названо число модулей — оно должно быть верным."""
    real = len(_engine_modules())
    for match in re.finditer(r"(\d+)\s+модул", APP_README + ROOT_README):
        stated = int(match.group(1))
        if 10 < stated < 200:                     # похоже на счётчик модулей
            assert stated == real, (
                f"в README указано {stated} модулей, фактически {real}"
            )


# ─── CLI ──────────────────────────────────────────────────────────────────────

def test_every_cli_command_is_documented():
    sys.path.insert(0, str(APP_ROOT))
    import cli
    undocumented = sorted(c for c in cli.COMMANDS
                          if f"cli.py {c}" not in APP_README)
    assert not undocumented, (
        "команды CLI без описания в README: " + ", ".join(undocumented)
    )


def test_readme_lists_only_real_cli_commands():
    sys.path.insert(0, str(APP_ROOT))
    import cli
    listed = set(re.findall(r"`cli\.py (\w+)`", APP_README))
    ghosts = sorted(listed - set(cli.COMMANDS))
    assert not ghosts, "README описывает несуществующие команды: " + ", ".join(ghosts)


# ─── Страницы ─────────────────────────────────────────────────────────────────

def _pages() -> set[str]:
    import tempfile
    import engine.db_core as dbc
    dbc.DB_PATH = Path(tempfile.mkdtemp()) / "docs.db"
    from engine.db_core import init_db
    init_db()
    from web.app import app
    return {
        str(r) for r in app.url_map.iter_rules()
        if "GET" in (r.methods or set())
        and not r.arguments
        and not str(r).startswith(("/api/", "/static"))
    }


def test_every_page_is_documented():
    undocumented = sorted(p for p in _pages() if f"`{p}`" not in APP_README)
    assert not undocumented, (
        "страницы без описания в README: " + ", ".join(undocumented)
    )


def test_knowledge_base_file_count_is_accurate():
    """Если README называет размер базы знаний — он должен сходиться."""
    kb = REPO_ROOT / "UNIFIED_ENGINE_MASTER"
    if not kb.exists():
        pytest.skip("база знаний не найдена")
    real = sum(1 for p in kb.rglob("*") if p.is_file())
    for match in re.finditer(r"(\d+)\s+файл", ROOT_README):
        stated = int(match.group(1))
        if stated > 50:                          # похоже на счётчик базы знаний
            assert stated == real, (
                f"в README указано {stated} файлов базы знаний, фактически {real}"
            )


def test_blueprint_count_is_accurate():
    bps = [f for f in (APP_ROOT / "web" / "blueprints").glob("*.py")
           if "Blueprint(" in f.read_text(encoding="utf-8")]
    for match in re.finditer(r"(\d+)\s+блупринт", APP_README):
        assert int(match.group(1)) == len(bps), (
            f"в README {match.group(1)} блупринтов, фактически {len(bps)}"
        )


# ─── Ссылки и окружение ───────────────────────────────────────────────────────

@pytest.mark.parametrize("readme,base", [("root", None), ("app", None)])
def test_referenced_files_exist(readme, base):
    text, root = (ROOT_README, REPO_ROOT) if readme == "root" else (APP_README, APP_ROOT)
    missing = []
    for link in re.findall(r"\]\(([^)#]+)\)", text):
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        if not (root / link).resolve().exists():
            missing.append(link)
    assert not missing, f"{readme} README ссылается на отсутствующие файлы: {missing}"


def test_documented_env_vars_are_read_by_code():
    """Переменная из таблицы README должна реально читаться кодом."""
    sources = ""
    for pattern in ("engine/*.py", "web/*.py", "web/blueprints/*.py"):
        for f in APP_ROOT.glob(pattern):
            sources += f.read_text(encoding="utf-8")
    for f in (REPO_ROOT / "planner").rglob("*.py"):
        sources += f.read_text(encoding="utf-8")

    documented = set(re.findall(r"\|\s*`([A-Z][A-Z_]+)`", ROOT_README))
    unused = sorted(v for v in documented
                    if f'"{v}"' not in sources and f"'{v}'" not in sources)
    assert not unused, (
        "README описывает переменные, которых код не читает: " + ", ".join(unused)
    )
