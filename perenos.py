"""
perenos.py — перенос данных Fiction Engine и Планировщика на другую машину.

Код лежит в git, а данные — нет: проекты и ключи провайдеров
(~/fiction_engine/projects.db), планы (planner/planner.db), настройки
(fiction_engine/.env), рабочие замеры (.ab_work) и переписка с Claude Code по
этому проекту (~/.claude/projects/<папка>/: сессии и память).

  python perenos.py pack   [архив.zip]   — собрать на старой машине
  python perenos.py unpack  архив.zip    — разложить на новой (из корня репозитория)
  python perenos.py init                 — .env и база, если их ещё нет (setup_windows.bat)
  python perenos.py wait 5000 5001       — ждать, пока приложения ответят (start_all.bat)

В архиве ключи API: передавать флешкой или кабелем, не выкладывать в сеть.
Существующие файлы на новой машине не затираются — откладываются с
суффиксом .before-perenos.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME_FE = Path.home() / "fiction_engine"
# Что из ~/fiction_engine переносить: логи и отладочные промпты не нужны
HOME_FILES = ("projects.db", "secret.key", "api_token")


def claude_dir(root: Path) -> Path:
    """Папка сессий Claude Code для проекта: путь, где всё не буква и не цифра — «-»."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root))


def _copy_db(src: Path, dst: Path) -> None:
    # Через backup, а не копированием файла: база может быть открыта приложением
    a, b = sqlite3.connect(src), sqlite3.connect(dst)
    with b:
        a.backup(b)
    a.close()
    b.close()


def pack(out: Path) -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        (tmp / "home").mkdir()
        for name in HOME_FILES:
            src = HOME_FE / name
            if not src.exists():
                continue
            if name.endswith(".db"):
                _copy_db(src, tmp / "home" / name)
            else:
                shutil.copy2(src, tmp / "home" / name)
        (tmp / "repo").mkdir()
        if (ROOT / "planner" / "planner.db").exists():
            _copy_db(ROOT / "planner" / "planner.db", tmp / "repo" / "planner.db")
        if (ROOT / "fiction_engine" / ".env").exists():
            shutil.copy2(ROOT / "fiction_engine" / ".env", tmp / "repo" / "fe.env")
        if (ROOT / ".ab_work").is_dir():
            shutil.copytree(ROOT / ".ab_work", tmp / "repo" / "ab_work")
        cd = claude_dir(ROOT)
        if cd.is_dir():
            shutil.copytree(cd, tmp / "claude")
        (tmp / "info.json").write_text(json.dumps({
            "from": str(ROOT), "date": datetime.datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False), encoding="utf-8")
        out = out.with_suffix("")
        shutil.make_archive(str(out), "zip", tmp)
    print(f"Готово: {out}.zip")
    print("В архиве ключи API — переносить флешкой или кабелем.")


def _put(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        keep = dst.with_name(dst.name + ".before-perenos")
        if keep.exists():
            shutil.rmtree(keep) if keep.is_dir() else keep.unlink()
        dst.rename(keep)
        print(f"  прежний {dst.name} отложен: {keep}")
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    print(f"  ✓ {dst}")


def _retarget_sessions(cd: Path, old: str) -> None:
    """В сессиях записана папка старой машины — меняем на новую, чтобы `claude --resume` их видел."""
    for f in cd.rglob("*.jsonl"):
        out = []
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                out.append(line)
                continue
            if isinstance(rec, dict) and rec.get("cwd", "").startswith(old):
                rec["cwd"] = str(ROOT) + rec["cwd"][len(old):].replace("/", "\\" if sys.platform == "win32" else "/")
            out.append(json.dumps(rec, ensure_ascii=False))
        f.write_text("\n".join(out) + "\n", encoding="utf-8")


def unpack(archive: Path) -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmp)
        info = json.loads((tmp / "info.json").read_text(encoding="utf-8"))
        print(f"Архив от {info['date']} из {info['from']}")
        for f in sorted((tmp / "home").glob("*")):
            _put(f, HOME_FE / f.name)
        repo = tmp / "repo"
        for src, dst in ((repo / "planner.db", ROOT / "planner" / "planner.db"),
                         (repo / "fe.env", ROOT / "fiction_engine" / ".env"),
                         (repo / "ab_work", ROOT / ".ab_work")):
            if src.exists():
                _put(src, dst)
        if (tmp / "claude").is_dir():
            cd = claude_dir(ROOT)
            _retarget_sessions(tmp / "claude", info["from"])
            cd.mkdir(parents=True, exist_ok=True)
            for f in sorted((tmp / "claude").iterdir()):
                _put(f, cd / f.name)
            print(f"Переписка с Claude: {cd}\n  продолжить — `claude --resume` из {ROOT}")
    print("Готово.")


def init() -> None:
    """.env со случайным ключом Flask и база (setup_windows.bat)."""
    import secrets
    env = ROOT / "fiction_engine" / ".env"
    if not env.exists():
        env.write_text(f"FLASK_SECRET_KEY={secrets.token_hex(32)}\n", encoding="utf-8")
        print(f"  ✓ создан {env}")
    (HOME_FE / "prompts_out").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "fiction_engine"))
    from engine.db import init_db
    init_db()
    print(f"  ✓ база {HOME_FE / 'projects.db'}")


def wait(ports: list[int], timeout: float = 120) -> bool:
    """Ждать ответа приложений: Fiction Engine поднимается дольше планировщика."""
    import time
    import urllib.error
    import urllib.request
    left = set(ports)
    end = time.monotonic() + timeout
    while left and time.monotonic() < end:
        for p in sorted(left):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{p}/", timeout=2)
                left.discard(p)
            except urllib.error.HTTPError:
                left.discard(p)         # ответил — пусть и ошибкой или входом
            except OSError:
                pass
        time.sleep(1)
    for p in sorted(left):
        print(f"  ✗ порт {p} не ответил за {int(timeout)} с — смотри текст ошибки в его окне")
    return not left


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "pack":
        pack(Path(argv[2]) if len(argv) > 2
             else Path.home() / f"fiction_engine_perenos_{datetime.date.today()}.zip")
        return 0
    if len(argv) == 2 and argv[1] == "init":
        init()
        return 0
    if len(argv) >= 3 and argv[1] == "wait":
        return 0 if wait([int(p) for p in argv[2:]]) else 1
    if len(argv) == 3 and argv[1] == "unpack":
        unpack(Path(argv[2]))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    # Консоль Windows без PYTHONUTF8 — cp1252/cp866, русский вывод падает
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
