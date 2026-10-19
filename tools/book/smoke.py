"""Дымовая книга: три главы на копии приложения — проверка движка целиком, как на настоящей книге.

    python tools/book/smoke.py              — поднять копию, написать книгу, проверить, погасить
    python tools/book/smoke.py --check DIR  — только проверки по готовому прогону в DIR

Зачем. Четыре ошибки «Фона» (19.10) нашлись только на настоящей книге: удаление
проекта (500), обрезка профиля голоса, рабочие заметки писателя в главе, дубль
персонажа с именем в скобках. Тесты их не ловили. Дымовая книга — короткий
фиксированный план (tools/book/smoke/book.json, 3 главы по 2 сцены) на копии FE
(:5300) и планировщика (:5301) из этой рабочей копии, со своей пустой базой.
Пишет его run_book.py «как автор» (BOOK_SMOKE: один круг правки, без проверки
логики и голоса), а после — проверки ниже. Гонять перед крупными изменениями
движка, вручную: вызовы моделей идут по подпискам, и одна подписка — один
процесс, поэтому не во время другой книги.

Проверки (плохо — код выхода 1):
  главы есть и не короче половины заданного объёма; нет рабочих заметок
  писателя; нет дублей персонажей в State; секрет из «Заметок автора» не ушёл
  ни в один запрос и ни в одну запись; забеганий нет; план вперёд дошёл до
  сторожа приложения; принят лучший по судье круг; откат последней главы
  возвращает State; проект удаляется. Противоречия библии — в отчёт.
"""
import json, os, re, sqlite3, subprocess, sys, time, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = Path(sys.executable)
BOOK_SRC = Path(__file__).parent / "smoke" / "book.json"
SECRET = "ДЫМ-СЕКРЕТ-7731"           # маркер в «Заметках автора» book.json
FE_PORT, PL_PORT = 5300, 5301


def env(work: Path) -> dict:
    home = work / "home"
    real = Path(os.path.expanduser("~"))
    # PYTHONPATH — код этой рабочей копии: иначе venv берёт установленный пакет из
    # основной папки, и копия гоняет не тот код (первый прогон 19.10: откат — 404)
    e = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", USERPROFILE=str(home), HOME=str(home),
             PYTHONPATH=os.pathsep.join([str(REPO / "fiction_engine"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep),
             FE_PORT=str(FE_PORT), PLANNER_PORT=str(PL_PORT), FE_URL=f"http://127.0.0.1:{FE_PORT}",
             PLANNER_DB=str(work / "planner.db"), FLASK_SECRET_KEY="smoke-book-secret-0123456789abcdef",
             BOOK_FE=f"http://127.0.0.1:{FE_PORT}", BOOK_PL=f"http://127.0.0.1:{PL_PORT}", BOOK_SMOKE="1",
             # Подписки: вход — из настоящих папок, база FE — из HOME копии
             FE_CLAUDE_SUBSCRIPTION="1", FE_CHATGPT_SUBSCRIPTION="1",
             CLAUDE_CONFIG_DIR=str(real / ".claude"), CODEX_HOME=str(real / ".codex"))
    for k in ("FE_PASSWORD", "PLANNER_PASSWORD"):
        e.pop(k, None)
    return e


def busy(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
        return True
    except Exception as ex:
        return hasattr(ex, "code")         # ответил ошибкой — порт занят


def start(work: Path) -> list:
    for port in (FE_PORT, PL_PORT):
        if busy(port):
            raise SystemExit(f"порт {port} занят — копия уже поднята или порт чужой; не трогаю")
    logs = work / "logs"
    logs.mkdir(exist_ok=True)
    e = env(work)
    procs = [subprocess.Popen([str(PY), "app.py"], cwd=str(REPO / "fiction_engine" / "web"), env=e,
                              stdout=open(logs / "fe.log", "a", encoding="utf-8"), stderr=subprocess.STDOUT),
             subprocess.Popen([str(PY), "app.py"], cwd=str(REPO / "planner"), env=e,
                              stdout=open(logs / "planner.log", "a", encoding="utf-8"), stderr=subprocess.STDOUT)]
    for port in (FE_PORT, PL_PORT):
        for _ in range(90):
            if busy(port):
                break
            time.sleep(1)
        else:
            stop(procs)
            raise SystemExit(f"порт {port} не поднялся — см. {logs}")
    return procs


def stop(procs: list) -> None:
    for p in procs:                       # только свои процессы, не всё на портах
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()


def fe(path: str, token: str, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{FE_PORT}{path}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-FE-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else {"raw": raw[:200]})
    except urllib.error.HTTPError as ex:
        return ex.code, {"raw": ex.read().decode("utf-8", "replace")[:300]}


def checks(work: Path, live: bool = True) -> list[tuple[str, bool, str]]:
    """[(проверка, прошла, подробность)]. live — копия поднята: откат и удаление через маршруты."""
    sys.path.insert(0, str(REPO / "fiction_engine"))
    from engine.pipeline_tasks import WORK_NOTE_MIN_LINES, work_note_lines
    book = json.loads((work / "book.json").read_text(encoding="utf-8"))
    setup = json.loads((work / "setup.json").read_text(encoding="utf-8"))
    res = json.loads((work / "results.json").read_text(encoding="utf-8")) if (work / "results.json").exists() else {"chapters": {}}
    pid, last = setup["fe_pid"], len(book["chapters"])
    db = work / "home" / "fiction_engine" / "projects.db"
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = []

    chapters = dict(c.execute("SELECT number, content FROM chapters WHERE project_id=?", (pid,)).fetchall())
    want = int(re.search(r"\d+", book.get("volume", "2800")).group()) // 2
    short = {n: len(t.split()) for n, t in chapters.items() if len(t.split()) < want}
    out.append(("главы 1–%d написаны" % last, sorted(chapters) == list(range(1, last + 1)) and not short,
                f"есть {sorted(chapters)}" + (f", короче {want} слов: {short}" if short else "")))
    notes = {n: len(work_note_lines(t)) for n, t in chapters.items() if len(work_note_lines(t)) >= WORK_NOTE_MIN_LINES}
    out.append(("нет рабочих заметок писателя", not notes, f"строк латиницей: {notes}" if notes else ""))

    st = c.execute("SELECT global_state FROM state_engine WHERE project_id=?", (pid,)).fetchone()
    heads = [re.sub(r"\s*\(.*?\)\s*$", "", h).strip().lower() for h in re.findall(r"^### (.+)$", st[0] if st else "", re.M)]
    dups = sorted({h for h in heads if heads.count(h) > 1})
    out.append(("нет дублей персонажей в State", not dups, ", ".join(dups)))

    # Секрет из «Заметок автора» — ни в одном запросе и ни в одной записи, кроме самой подготовки
    leaks = []
    for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        if table in ("prep_data", "sqlite_sequence"):
            continue
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})") if (r[2] or "").upper() in ("TEXT", "")]
        for col in cols:
            n = c.execute(f"SELECT count(*) FROM {table} WHERE CAST({col} AS TEXT) LIKE ?", (f"%{SECRET}%",)).fetchone()[0]
            if n:
                leaks.append(f"{table}.{col} ×{n}")
    out.append(("«Заметки автора» никуда не ушли", not leaks, ", ".join(leaks)))

    ahead = {n: [x for x in (r.get("run_ahead") or []) if "раскрыт" in str(x.get("kind", ""))]
             for n, r in res["chapters"].items()}
    out.append(("забеганий нет (внешний сторож)", not any(ahead.values()),
                "; ".join(f"гл.{n}: {x.get('why', '')[:80]}" for n, xs in ahead.items() for x in xs)))
    app = {n: [x for rd in (r.get("rounds") or []) for x in (rd.get("app_ahead") or []) if x.get("kind") == "раскрытие"]
           for n, r in res["chapters"].items()}
    out.append(("сторож приложения (в отчёт)", True,
                "; ".join(f"гл.{n}: {len(xs)} раскрытий по кругам" for n, xs in app.items() if xs) or "раскрытий нет"))
    try:
        fut = dict(c.execute("SELECT chapter_num, length(text) FROM chapter_future_plans WHERE project_id=?",
                             (pid,)).fetchall())
    except sqlite3.OperationalError:
        fut = {}
    need = set(range(1, last))
    out.append(("план вперёд дошёл до сторожа приложения", need <= set(fut), f"есть для глав {sorted(fut)}"))

    worse = []
    for n, r in res["chapters"].items():
        rounds = r.get("rounds") or []
        if rounds and r.get("accepted_round"):
            # Выбор приложения (балл судьи и план, pipeline.best_round); нет его — лучший по судье
            best = r.get("app_best") or max(
                rounds, key=lambda x: (x.get("verdict") == "ПРИНЯТЬ", float(x.get("judge_score") or 0), x["round"]))["round"]
            if best != r["accepted_round"]:
                worse.append(f"гл.{n}: принят {r['accepted_round']}, лучший {best}")
    out.append(("принят лучший круг (судья и план)", not worse, "; ".join(worse)))

    conflicts = c.execute("SELECT chapter_num, name, attr, value, reason FROM series_bible WHERE project_id=? "
                          "AND status='противоречие'", (pid,)).fetchall()
    out.append(("противоречия библии (в отчёт)", True,
                "; ".join(f"гл.{r[0]} {r[1]} — {r[2]}: «{r[3]}», {r[4]}" for r in conflicts) or "нет"))
    c.close()

    if live:
        token = (work / "home" / "fiction_engine" / "api_token").read_text().strip()
        code, info = fe(f"/chapter/{last}/rollback", token)
        code2, rb = fe(f"/chapter/{last}/rollback", token, {})
        out.append(("откат последней главы возвращает State", code2 == 200 and bool(rb.get("state_restored")),
                    f"снимок {info.get('snapshot')}, ответ {code2} {rb}"))
        code, _ = fe(f"/project/{pid}/delete", token, {})
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        gone = not c.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone()
        out.append(("проект удаляется", code in (200, 302) and gone, f"ответ {code}"))
    return out


def report(work: Path, rows: list) -> bool:
    ok = all(r[1] for r in rows)
    lines = [f"{'✓' if r[1] else '✗'} {r[0]}" + (f" — {r[2]}" if r[2] else "") for r in rows]
    text = f"Дымовая книга: {work}\n" + "\n".join(lines) + f"\n\nИТОГ: {'всё прошло' if ok else 'есть поломки'}\n"
    (work / "smoke_report.txt").write_text(text, encoding="utf-8")
    print(text)
    return ok


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        work = Path(sys.argv[2]).resolve()
        return 0 if report(work, checks(work, live=False)) else 1
    work = REPO / ".ab_work" / "smoke" / time.strftime("%Y%m%d-%H%M")
    (work / "home" / "fiction_engine").mkdir(parents=True, exist_ok=True)
    (work / "book.json").write_text(BOOK_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    procs = start(work)
    try:
        e = env(work)
        token = (work / "home" / "fiction_engine" / "api_token").read_text().strip()
        print("набор ролей:", fe("/pipeline/preset", token, {"name": "sonnet"}))
        for script, args in (("setup_book.py", []), ("run_book.py", ["1", str(len(json.loads(BOOK_SRC.read_text(encoding="utf-8"))["chapters"]))])):
            r = subprocess.run([str(PY), str(REPO / "tools" / "book" / script), *args], cwd=str(work), env=e)
            if r.returncode:
                print(f"{script}: код {r.returncode} — проверки по тому, что успело написаться")
                break
        return 0 if report(work, checks(work)) else 1
    finally:
        stop(procs)


if __name__ == "__main__":
    sys.exit(main())
