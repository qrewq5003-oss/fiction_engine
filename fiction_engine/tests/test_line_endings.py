"""
Файлы репозитория — с LF (кроме .bat, см. .gitattributes).

18.10 скрипты правки на Windows (Python пишет «\r\n» в текстовом режиме)
перевели 16 файлов на CRLF: диф каждого PR — весь файл целиком, история
правок по строкам пропала. Проверяется то, что лежит в индексе git.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_no_crlf_in_repository():
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("нет git")
    out = subprocess.run(["git", "ls-files", "--eol"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8").stdout
    crlf = [line.split()[-1] for line in out.splitlines()
            if line.startswith("i/crlf") and not line.endswith(".bat")]
    assert not crlf, "файлы с CRLF (нужен LF): " + ", ".join(crlf)
