"""Снимок заданий главы: что получает каждая модель — без вызовов моделей.

    python tools/prompt_snapshot.py PROJECT_ID CHAPTER [OUT_DIR]

Глава проходит путь автора в приложении на КОПИИ базы (рабочая только
читается): «Промпт писателя» → «Мастерская» (писатель, сверка, критик,
судья) → сверка с планом → «Ещё круг редактуры» → «Принять» с фоном после
него (State, L3, заметка). Вместо модели — заглушка: записывает задание и
отвечает болванкой (глава-болванка, разбор и вердикт по формату, JSON по
образцу из задания с пустыми списками). Живой вызов запрещён.

Задача и роли — из последнего запуска этой главы в базе.

В OUT_DIR (по умолчанию ~/fiction_engine/snapshots/p<проект>-ch<N> — там текст
книги, в репозиторий не кладётся): calls/ —
каждое задание целиком, report.md и report.json — проверки:

- БУДУЩЕЕ: текст глав с номером больше этой главы в задании;
- ОБРЕЗ: модель видит не весь текст главы, которую оценивает;
- ЭТА ГЛАВА: писатель видит прежний текст главы, которую пишет заново;
- ЗАМЕТКИ: раздел подготовки «Заметки» (только для автора) в задании;
- ЗАГЛУШКИ: «[Вставь …]», {имя}, None, nan в задании;
- ПОРОГ: в задании судьи порог «≥ N», которого нет в правиле вердикта кода;
- ИСТОРИЯ: в истории оценок судьи — эта глава или следующие;
- СЕМЬЯ: текст оценивает модель той же семьи, что писатель;
- ПОВТОР: один и тот же большой кусок дважды в одном задании.

Найдено так (вручную) 20.10: эталон голоса для гл.12 «Фона» из гл.23–24,
дрейф голоса по первым 1200 символам, судье — история с этой главой.
Код выхода — число ошибок (БУДУЩЕЕ, ОБРЕЗ, ЗАМЕТКИ, ЗАГЛУШКИ, ПОРОГ).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
# Консоль Windows (cp1251/cp866) падала на «→» и «≥» в выводе (разбор 21.10)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import tempfile
import threading
from collections import Counter
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
# Подписки включены, как у автора: иначе выбор проверяющих и State идут по
# другой ветке, чем в приложении (вызова всё равно не будет — заглушка)
os.environ.setdefault("FE_CHATGPT_SUBSCRIPTION", "1")
os.environ.setdefault("FE_CLAUDE_SUBSCRIPTION", "1")

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "fiction_engine"
sys.path.insert(0, str(APP))

K = 8                          # слов в шингле: короче — совпадают обычные обороты
MIN_HIT = 20                   # слов совпадения, ниже — случайность
JUDGE_HISTORY = re.compile(r"ИСТОРИЯ ОЦЕНОК ПРОЕКТА:([^\n]*)")
PLACEHOLDERS = [
    (re.compile(r"\[\s*Вставь[^\]]*\]", re.I), "заглушка «[Вставь …]»"),
    (re.compile(r"(?<![{\\])\{[a-z_]{3,}\}(?!\})"), "неподставленное {имя}"),
    (re.compile(r"(?<![\w.])None(?![\w.])"), "None в тексте"),
    (re.compile(r"(?<![\w.])nan(?![\w.])"), "nan в тексте"),
]
ERRORS = ("БУДУЩЕЕ", "ОБРЕЗ", "ЗАМЕТКИ", "ЗАГЛУШКИ", "ПОРОГ")


# ─── Копия базы ───────────────────────────────────────────────────────────────

def copy_db() -> Path:
    """Копия рабочей базы через backup SQLite (с WAL); рабочая открыта только на чтение."""
    src = Path.home() / "fiction_engine" / "projects.db"
    tmp = Path(tempfile.mkdtemp(prefix="snap_"))
    dst = tmp / "projects.db"
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as s, sqlite3.connect(dst) as d:
        s.backup(d)
    import atexit
    atexit.register(shutil.rmtree, tmp, True)
    return dst


# ─── Заглушка модели ──────────────────────────────────────────────────────────

def fake_chapter(n: int) -> str:
    """Глава-болванка ~2800 слов: абзацы, реплики, свои слова — чтобы её куски узнавались."""
    lines = ["Утро было серым, и в подъезде пахло мокрой штукатуркой.",
             "Она поднялась на третий этаж и остановилась у двери с облезлым номером.",
             "За стеной кто-то двигал стул, потом всё стихло.",
             "Телефон в кармане дрогнул, но она не стала смотреть.",
             "На подоконнике лежала связка ключей, которой вчера здесь не было."]
    out = []
    for p in range(1, 71):
        body = " ".join(f"Сцена {n} абзац {p} строка {s}. {lines[(p + s) % len(lines)]}" for s in range(1, 6))
        out.append(body)
        if p % 3 == 0:
            out.append(f"— Реплика {p} главы {n}, — сказал Гоша. — Ты это видела?")
    return "\n\n".join(out) + "\n\nОна закрыла дверь и выключила свет."


CRITIQUE = """ГОЛОС: 7 — ровно
СТРУКТУРА: 6 — провисает середина
ПЕРСОНАЖИ: 7 — мотивы видны
СЦЕНЫ: 6 — есть пересказ
ДИАЛОГ: 7 — живой
ИТОГ: 33
ПРОБЛЕМЫ:
1. «Сцена» — середина пересказана."""


def judgment(total: int) -> str:
    v = "ПРИНЯТЬ" if total >= 33 else "НА ДОРАБОТКУ"
    per = [7, 6, 7, 6, 7] if total >= 33 else [6, 5, 6, 5, 6]
    names = ("ГОЛОС", "СТРУКТУРА", "ПЕРСОНАЖИ", "СЦЕНЫ", "ДИАЛОГ")
    return "\n".join([f"{k}: {s} — за дело" for k, s in zip(names, per)]
                     + [f"ИТОГ: {total}", "СВЯЗНОСТЬ: ОК — нет", "УЛУЧШЕНИЯ: —", "ОСТАТОК: —",
                        f"ВЕРДИКТ: {v}", "ОБОСНОВАНИЕ: по баллам"])


def _empty_lists(x):
    if isinstance(x, list):
        return []
    if isinstance(x, dict):
        return {k: _empty_lists(v) for k, v in x.items()}
    return x


def json_like(text: str) -> str | None:
    """JSON по образцу из задания, списки пустые; образца нет — None."""
    at = text.rfind("JSON")
    if at < 0:
        return None
    dec = json.JSONDecoder()
    found, end = None, 0
    for m in re.finditer(r"[\[{]", text):
        if m.start() < end:              # внутри уже разобранного образца — берём внешний
            continue
        try:
            obj, end = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, (dict, list)) and (obj or found is None):
            found = obj
    if found is None:
        return "[]" if "массив" in text[at:at + 400].lower() else "{}"
    return json.dumps(_empty_lists(found), ensure_ascii=False)


SKIP = {"call", "_call", "call_llm", "call_model", "stub", "ask", "<lambda>", "_budgeted",
        "wrapper", "inner", "_wrapped", "decorated", "caller", "_proxy", "api_call_fn", "fn"}
# Задания, где модель судит текст главы (Claude не судит Claude); извлечение
# фактов (анализ, State, L3) и правка — не суд
JUDGING = {"step_critique", "step_judge", "check_voice_drift", "score_text", "check_plan",
           "run_ahead_for", "check_continuity", "check_against_chapters", "filter_edits",
           "analyze_voice_match"}


def caller_chain(depth: int = 4) -> list[str]:
    f = sys._getframe(2)
    chain: list[str] = []
    while f and len(chain) < depth:
        path = f.f_code.co_filename.replace("\\", "/")
        name = f.f_code.co_name
        if ("/engine/" in path or "/web/" in path) and name not in SKIP \
                and not path.endswith(("/engine/api.py", "/error_policy.py")):
            chain.append(name)
        f = f.f_back
    return chain or ["?"]


class Stub:
    def __init__(self, chapter: int):
        self.chapter = chapter
        self.text = fake_chapter(chapter)
        self.calls: list[dict] = []
        self.judged = 0
        self.lock = threading.Lock()

    def __call__(self, model_value, system, user, *a, max_tokens=None, prefill="", **kw):
        chain = caller_chain()
        with self.lock:
            rec = {"n": len(self.calls) + 1, "caller": chain, "model": model_value,
                   "max_tokens": max_tokens, "system": system or "", "user": user or "",
                   "thread": threading.current_thread().name}
            self.calls.append(rec)
            head = chain[0]
            if head in ("step_generate", "extend_short_chapter", "_without_work_notes"):
                ans = self.text
            elif head == "step_critique":
                ans = CRITIQUE
            elif head == "step_judge":
                self.judged += 1
                ans = judgment(29 if self.judged == 1 else 34)
            elif head == "step_edit":        # переписывание целиком (режим rewrite)
                ans = self.text
            else:
                ans = json_like(f"{system}\n{user}") or "ОЦЕНКА: 8/10\nЗамечаний нет."
            rec["answer"] = ans[:300]
            return ans


def install(stub: Stub):
    """call_model → заглушка во всех модулях; провайдеры и лимиты — отказ/пусто. → откат."""
    import engine.api as api
    import engine.pipeline_drift as drift
    real = api.call_model
    saved = []

    def put(obj, attr, value):
        saved.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, value)

    for mod in list(sys.modules.values()):
        name = getattr(mod, "__name__", "") or ""
        if name.split(".")[0] in ("engine", "web") and getattr(mod, "call_model", None) is real:
            put(mod, "call_model", stub)

    def refuse(*a, **k):
        raise RuntimeError("снимок заданий: живой вызов модели запрещён")
    for attr in dir(api):
        if attr.startswith("_call_"):
            put(api, attr, refuse)
    put(api, "chatgpt_limits", lambda: {})
    # Дрейф голоса идёт раз в несколько глав — в снимке всегда, чтобы его задание было видно
    put(drift, "should_check_drift", lambda *a, **k: True)

    def undo():
        for obj, attr, value in reversed(saved):
            setattr(obj, attr, value)
    return undo


# ─── Проверки ─────────────────────────────────────────────────────────────────

def toks(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower().replace("ё", "е"))


def shingles(t: list[str]) -> list[int]:
    return [hash(tuple(t[i:i + K])) for i in range(max(len(t) - K + 1, 0))]


def coverage(ch_sh: list[int], n_tok: int, have: set[int]) -> tuple[float, list[tuple[int, int]]]:
    """→ (доля главы в задании, куски подряд от MIN_HIT слов — номера слов главы)."""
    mask = bytearray(n_tok)
    for i, h in enumerate(ch_sh):
        if h in have:
            mask[i:i + K] = b"\1" * K
    spans, start = [], None
    for i, m in enumerate(list(mask) + [0]):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start >= MIN_HIT:
                spans.append((start, i))
            start = None
    return sum(e - s for s, e in spans) / max(n_tok, 1), spans


def describe(spans: list[tuple[int, int]], n_tok: int, words: list[str]) -> str:
    """Куски главы: где (в % главы), сколько слов и с чего начинается."""
    return "; ".join(f"{round(100 * s / n_tok)}–{round(100 * e / n_tok)} %, {e - s} сл. «{' '.join(words[s:s + 8])}…»"
                     for s, e in spans[:4]) + (f"; ещё {len(spans) - 4}" if len(spans) > 4 else "")


def family(m: str) -> str:
    """Семья модели — правилом приложения (pipeline_config.model_family). Своя
    копия относила Kimi через nano_gpt к «gpt» (разбор 21.10)."""
    from engine.pipeline_config import model_family
    return model_family(m or "")


def blocks(text: str) -> list[tuple[str, int]]:
    """Заголовки блоков задания (строка заглавными) и их размер в символах."""
    heads = [(m.start(), m.group(1).strip(" \t=═:#-—"))
             for m in re.finditer(r"(?m)^([ \t=═#\-—]*[А-ЯЁA-Z][А-ЯЁA-Z0-9 ,()«»/\-—]{3,70}[ \t=═:]*)$", text)
             if sum(c.isupper() for c in m.group(1)) >= 4]
    out = []
    for i, (pos, name) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        out.append((name, end - pos))
    return out


def check(calls: list[dict], chapters: dict[int, str], current: int, fake: str,
          notes: str, writer: str, accept_total: dict[str, int]) -> list[dict]:
    found: list[dict] = []

    def add(kind, call, msg):
        found.append({"kind": kind, "call": call["n"], "caller": call["caller"][0], "msg": msg})

    idx = {}
    for n, t in {**chapters, "круг": fake}.items():
        tt = toks(t)
        idx[n] = (shingles(tt), len(tt), tt)
    notes_t = toks(notes) if notes.strip() else []
    notes_sh = set(shingles(notes_t))
    for c in calls:
        full = f"{c['system']}\n{c['user']}"
        have = set(shingles(toks(full)))
        c["chapters"] = {}
        for n, (sh, nt, words) in idx.items():
            share, spans = coverage(sh, nt, have)
            if not spans:
                continue
            c["chapters"][n] = {"share": round(share, 3), "where": describe(spans, nt, words)}
            if n == "круг":
                # Обрез — там, где модель судит главу; заметка к следующей главе берёт конец нарочно
                if share < 0.95 and JUDGING & set(c["caller"]):
                    add("ОБРЕЗ", c, f"текст главы виден на {round(100 * share)} %: {describe(spans, nt, words)}")
                if family(c["model"]) == family(writer) and JUDGING & set(c["caller"]):
                    add("СЕМЬЯ", c, f"{c['model']} судит текст {writer}")
            elif n > current:
                add("БУДУЩЕЕ", c, f"гл.{n}: {describe(spans, nt, words)}")
            elif n == current and c["caller"][0] == "step_generate":
                add("ЭТА ГЛАВА", c, f"писатель видит прежний текст этой главы: {describe(spans, nt, words)}")
        if notes_sh and len(have & notes_sh) * 1.0 / max(len(notes_sh), 1) > 0.05:
            add("ЗАМЕТКИ", c, f"«Заметки» автора: {round(100 * len(have & notes_sh) / len(notes_sh))} % раздела")
        for rx, what in PLACEHOLDERS:
            for m in rx.finditer(full):
                ctx = full[max(m.start() - 60, 0):m.end() + 40].replace("\n", " ")
                add("ЗАГЛУШКИ", c, f"{what}: …{ctx}…")
                break
        if c["caller"][0] == "step_judge":
            want = accept_total.get(c["model"])
            for m in re.finditer(r"≥\s*(\d{2})\b", c["system"]):
                if want and int(m.group(1)) != want:
                    ctx = c["system"][max(m.start() - 80, 0):m.end() + 30].replace("\n", " ")
                    add("ПОРОГ", c, f"«≥ {m.group(1)}» при правиле кода {want}: …{ctx}…")
            h = JUDGE_HISTORY.search(c["system"])
            if h:
                late = sorted({int(x) for x in re.findall(r"гл\.\s*(\d+)", h.group(1)) if int(x) >= current})
                if late:
                    add("ИСТОРИЯ", c, f"в истории оценок главы {late} (эта глава — {current}): {h.group(1).strip()}")
        paras = [p.strip() for p in re.split(r"\n\s*\n", full) if len(p.strip()) >= 300]
        for p, k in Counter(paras).items():
            if k > 1:
                add("ПОВТОР", c, f"×{k}, {len(p)} симв.: «{p[:80]}…»")
    return found


# ─── Прогон ───────────────────────────────────────────────────────────────────

def last_run(db: Path, pid: int, n: int) -> tuple[str, dict]:
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        run = c.execute("SELECT * FROM pipeline_runs WHERE project_id=? AND chapter_num=? ORDER BY id DESC LIMIT 1",
                        (pid, n)).fetchone()
        if not run:
            raise SystemExit(f"у главы {n} проекта {pid} нет запусков — задачу и роли брать неоткуда")
        it = c.execute("SELECT input_text FROM pipeline_iterations WHERE run_id=? AND stage='generate' "
                       "ORDER BY id LIMIT 1", (run["id"],)).fetchone()
    roles = {k: run[k] for k in ("model_gen", "model_critic", "model_editor", "model_judge")}
    return (it["input_text"] if it else "") or "", roles


def main() -> int:
    pid, n = int(sys.argv[1]), int(sys.argv[2])
    # Снимок — текст книги автора: по умолчанию рядом с базой, не в репозитории
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path.home() / "fiction_engine" / "snapshots" / f"p{pid}-ch{n}"
    db = copy_db()
    import engine.db_core as dbc
    dbc.DB_PATH = db
    task, roles = last_run(db, pid, n)
    calls, found, steps = snapshot(pid, n, task, roles)
    write(out, pid, n, roles, steps, calls, found)
    errors = [f for f in found if f["kind"] in ERRORS]
    print(f"{len(calls)} заданий, ошибок {len(errors)}, замечаний {len(found) - len(errors)} → {out / 'report.md'}")
    return len(errors)


def snapshot(pid: int, n: int, task: str, roles: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Путь главы в приложении на текущей базе (engine.db_core.DB_PATH) → (задания, находки, шаги)."""
    import engine.db_core as dbc
    with sqlite3.connect(dbc.DB_PATH) as c:
        chapters = {r[0]: r[1] or "" for r in c.execute(
            "SELECT number, content FROM chapters WHERE project_id=? ORDER BY number", (pid,))}
        notes = (c.execute("SELECT content FROM prep_data WHERE project_id=? AND section='notes'",
                           (pid,)).fetchone() or [""])[0] or ""

    from web.app import app
    from engine.pipeline_config import accept_total_for
    stub = Stub(n)
    undo = install(stub)
    try:
        steps = _walk(app, pid, n, task, roles, stub)
    finally:
        undo()
    found = check(stub.calls, chapters, n, stub.text, notes, roles["model_gen"],
                  {m: accept_total_for(m) for m in set(roles.values())})
    return stub.calls, found, steps


def _walk(app, pid: int, n: int, task: str, roles: dict, stub: Stub) -> list[dict]:
    from engine.db_settings import set_active_project
    set_active_project(pid)
    app.config.update(TESTING=True, FE_CSRF=False)
    cl = app.test_client()
    steps: list[dict] = []

    def post(path, body):
        r = cl.post(path, json=body)
        data = r.get_json(silent=True) or {}
        steps.append({"path": path, "code": r.status_code, "error": data.get("error")})
        return data

    post("/pipeline/preview", {"chapter_num": n, "task": task, "engine_mode": "quick",
                               "model_gen": roles["model_gen"]})
    r = post("/pipeline/start", {"chapter_num": n, "generation_prompt": task, "engine_mode": "quick",
                                 "review": True, **roles})
    run_id = r.get("run_id")
    text = r.get("generated_text") or stub.text
    post("/pipeline/plan_check", {"chapter_num": n, "text": text, "run_id": run_id,
                                  "model_gen": roles["model_gen"]})
    if run_id:
        r = post("/pipeline/continue", {"run_id": run_id, "chapter_num": n, "generation_prompt": task,
                                        "previous_text": text, "previous_critique": r.get("critique") or ""})
        before = set(threading.enumerate())
        post("/pipeline/accept", {"run_id": run_id, "chapter_num": n, "final_text": r.get("generated_text") or text,
                                  "model_value": roles["model_gen"]})
        for t in set(threading.enumerate()) - before:
            t.join(timeout=300)
    return steps


def write(out: Path, pid: int, n: int, roles: dict, steps: list, calls: list, found: list) -> None:
    if out.exists():
        shutil.rmtree(out)
    (out / "calls").mkdir(parents=True)
    for c in calls:
        name = f"{c['n']:02d}_{c['caller'][0]}.txt"
        c["file"] = f"calls/{name}"
        (out / "calls" / name).write_text(
            f"# вызов {c['n']}: {' < '.join(c['caller'])}\n# модель: {c['model']}, max_tokens: {c['max_tokens']}, "
            f"поток: {c['thread']}\n\n===== SYSTEM ({len(c['system'])} симв.) =====\n{c['system']}\n\n"
            f"===== USER ({len(c['user'])} симв.) =====\n{c['user']}\n\n===== ОТВЕТ ЗАГЛУШКИ =====\n{c['answer']}\n",
            encoding="utf-8", newline="\n")
    md = [f"# Снимок заданий: проект {pid}, глава {n}", "",
          "Роли: " + ", ".join(f"{k} = {v}" for k, v in roles.items()), "",
          "Шаги: " + "; ".join(f"{s['path']} {s['code']}" + (f" ({s['error']})" if s["error"] else "") for s in steps),
          "", f"## Находки ({len(found)})", ""]
    for kind in ERRORS + ("ЭТА ГЛАВА", "ИСТОРИЯ", "СЕМЬЯ", "ПОВТОР"):
        items = [f for f in found if f["kind"] == kind]
        if items:
            md.append(f"### {kind}{' — ошибка' if kind in ERRORS else ''} ({len(items)})")
            md += [f"- вызов {f['call']} `{f['caller']}`: {f['msg']}" for f in items] + [""]
    md += ["## Задания", "", "| # | кто | модель | system | user | главы в задании (доля главы) |",
           "|---|---|---|---|---|---|"]
    for c in calls:
        chs = ", ".join(f"{k}: {max(round(100 * v['share']), 1)} %" for k, v in c["chapters"].items())
        md.append(f"| [{c['n']}]({c['file']}) | {' < '.join(c['caller'][:2])} | {c['model'].split('::')[-1]} | "
                  f"{len(c['system'])} | {len(c['user'])} | {chs} |")
    md += ["", "## Крупные блоки заданий", ""]
    for c in calls:
        big = sorted(blocks(c["system"] + "\n" + c["user"]), key=lambda b: -b[1])[:6]
        if big:
            md.append(f"- {c['n']} `{c['caller'][0]}`: " + ", ".join(f"{b[0][:50]} {b[1]}" for b in big))
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    (out / "report.json").write_text(json.dumps(
        {"project": pid, "chapter": n, "roles": roles, "steps": steps, "found": found,
         "calls": [{k: v for k, v in c.items() if k not in ("system", "user")} for c in calls]},
        ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(main())
