"""Книга в приложении автора (FE :5000, планировщик :5001) — главы пишутся «как автор».

    cd ПАПКА_КНИГИ && python tools/book/run_book.py [первая_глава] [последняя_глава]

Папка книги: book.json (подготовка, голос, план глав) и setup.json от setup_book.py.
Порядок работы и уроки — tools/book/README.md. Роли — из book.json "roles", иначе набор Sonnet.

Глава: сцены в планировщике → экспорт плана → «Мастерская» (писатель, проверка
непрерывности, критик, судья) → сверка с планом → при доработке или пропусках
«Ещё круг редактуры» с правкой задачи → «Принять» → ждём State, L3, заметку.
После главы — снимок структуры: State, библия, L3, промпт следующей главы.
"""
import json, os, re, sqlite3, sys, time
# Консоль Windows (cp1251/cp866) падала на «→» и «≥» в выводе (разбор 21.10)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
import requests

B = Path.cwd()                       # папка книги
REPO = Path(__file__).resolve().parents[2]
BOOK = json.load(open(B / "book.json", encoding="utf-8"))
# Копия приложения (дымовая книга, tools/book/smoke.py) — свои адреса и облегчённый прогон
FE = os.environ.get("BOOK_FE", "http://127.0.0.1:5000")
PL = os.environ.get("BOOK_PL", "http://127.0.0.1:5001")
SMOKE = os.environ.get("BOOK_SMOKE") == "1"
# BOOK_TASK=assist — задачу главы готовит кнопка «Подготовить промт»; у главы без "task" — всегда
ASSIST = os.environ.get("BOOK_TASK") == "assist"
# BOOK_TASK=plain — в поле задачи только «Напиши главу N.»: всё остальное — план из планировщика
PLAIN = os.environ.get("BOOK_TASK") == "plain"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fe_auth                                          # noqa: E402
H = fe_auth.headers()
DB = Path.home() / "fiction_engine" / "projects.db"
SETUP = json.load(open(B / "setup.json", encoding="utf-8"))
PID = SETUP["fe_pid"]
PL_PID = SETUP["pl_pid"]
LAST = len(BOOK["chapters"])
NANO = "nano_gpt::"
SONNET = "claude_subscription::claude-sonnet-5-5@xhigh"
SOL = "chatgpt_subscription::gpt-6.1-sol@xhigh"
ROLES = BOOK.get("roles") or {"model_gen": SONNET, "model_critic": "claude_subscription::claude-haiku-5-5@xhigh",
                              "model_editor": SONNET, "model_judge": SOL}
MAX_EXTRA = 1 if SMOKE else 2
OUT = B / "results.json"
results = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"chapters": {}}


def log(*a):
    s = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(B / "run.log", "a", encoding="utf-8") as f:
        f.write(s + "\n")


def save():
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


def fe(path, body=None, timeout=3600):
    r = (requests.post(FE + path, json=body, headers=H, timeout=timeout) if body is not None
         else requests.get(FE + path, headers=H, timeout=timeout))
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}


# ─── Планировщик ──────────────────────────────────────────────────────────────
pl = requests.Session()


def pl_csrf():
    html = pl.get(PL + "/projects", timeout=30).text
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def pl_post(path, body):
    r = pl.post(PL + path, json=body, headers={"X-CSRF-Token": pl_csrf()}, timeout=600)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}


def planner_setup():
    # Проект планировщика заведён setup.py; выбор — в сессии скрипта, вид автора не меняется
    pl.get(PL + f"/switch/{PL_PID}", timeout=30)


def act_for(n):
    acts = pl.get(PL + "/api/acts", timeout=30).json()["acts"]
    acts.sort(key=lambda a: a["number"])
    return acts[0 if n <= 8 else 1 if n <= 16 else 2]["id"]


def planner_chapter(n, ch):
    # Сцены этой главы уже заведены и отправлены (перезапуск) — те же
    have = [s["id"] for s in pl.get(PL + "/api/scenes", timeout=30).json()["scenes"] if s.get("chapter_num") == n]
    if have:
        return have, pl_post("/api/export/send", {"scene_ids": have, "chapter_num": n})[1]
    # План всей книги уже на доске (book.json "plan_ahead", setup_book) — сцены главы по названию
    if BOOK.get("plan_ahead"):
        free = [s for s in pl.get(PL + "/api/scenes", timeout=30).json()["scenes"] if not s.get("chapter_num")]
        ids = [next(s["id"] for s in free if s["title"] == sc["title"]) for sc in ch["scenes"]]
        return ids, pl_post("/api/export/send", {"scene_ids": ids, "chapter_num": n})[1]
    ids = []
    act = act_for(n)
    for s in ch["scenes"]:
        code, r = pl_post("/api/scenes/new", {"act_id": act, "title": s["title"], "location": s["location"],
                                              "day": s.get("day", ""), "time_of_day": s["time"], "characters": s["chars"],
                                              "what_happens": s["what"], "emotion": s["emo"],
                                              "hold": s.get("hold", "")})
        ids.append(r["id"])
    code, r = pl_post("/api/export/send", {"scene_ids": ids, "chapter_num": n})
    return ids, r


# ─── Снимок структуры ─────────────────────────────────────────────────────────

def snapshot(n):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    st = c.execute("select * from state_engine where project_id=?", (PID,)).fetchone()
    g, p, m = (st["global_state"], st["plot_matrix"], st["memory_graph"]) if st else ("", "", "")
    heads = re.findall(r"^### (.+)$", g, re.M)
    dup = sorted({h for h in heads if heads.count(h) > 1})
    sections = re.findall(r"^## (.+)$", p, re.M)
    where = re.search(r"ГДЕ_СЕЙЧАС:\s*(.*)", p)
    snap = {
        "state_chars": len(g) + len(p) + len(m), "global": len(g), "plot": len(p), "memory": len(m),
        "characters": heads, "dup_characters": dup,
        "dup_sections": sorted({s for s in sections if sections.count(s) > 1}),
        "where_now": where.group(1)[:200] if where else None,
        "double_prefix": len(re.findall(r"гл\.\d+:\s*гл\.\d+:", p)),
        "crlf": "\r" in (g + p + m),
        "open_questions": len(re.findall(r"^- гл\.\d+:", p, re.M)),
        "l3": [r[0] for r in c.execute("select chapter_num from l3_memory where project_id=? order by chapter_num", (PID,))],
        "notes": {r[0]: r[1][:160] for r in c.execute("select after_chapter, note from director_notes where project_id=?", (PID,))},
        "bible_rows": c.execute("select count(*) from series_bible where project_id=?", (PID,)).fetchone()[0],
        "pending_updates": c.execute("select count(*) from state_updates where project_id=? and applied=0", (PID,)).fetchone()[0],
        "chapters": [r[0] for r in c.execute("select number from chapters where project_id=? order by number", (PID,))],
    }
    try:
        snap["bible_conflicts"] = len(fe(f"/api/bible?pid={PID}")[1].get("conflicts", []))
    except Exception as e:
        snap["bible_conflicts"] = repr(e)[:80]
    return snap


def wait_after_accept(n, job):
    t0 = time.time()
    while job and time.time() - t0 < 900:
        code, r = fe(f"/pipeline/state_status/{job}")
        if r.get("status") == "done":
            log(f"  State обновлён: {r.get('state_updated')} за {round(time.time() - t0)} с")
            break
        time.sleep(10)
    # L3 и заметка к следующей главе — после State, в том же фоне
    while time.time() - t0 < 1200:
        s = snapshot(n)
        if n in s["l3"] and (n == LAST or n in s["notes"]):
            break
        time.sleep(15)
    log(f"  после принятия ждали {round(time.time() - t0)} с")


# ─── Сторож забеганий и лимитов ───────────────────────────────────────────────
# Sol: текст пишет Sonnet, сторож — другое семейство. DeepSeek путал известное о мире с раскрытием
# (гл.1: «Кравец — фельдшер», «Митяй браконьерит» — из «Подготовки») и пропускал настоящее забегание
CHECKER = ROLES["model_judge"]     # проверки — судья набора: другая семья, чем писатель
AHEAD_MODEL = CHECKER
LIMIT_WORDS = ("usage limit", "rate limit", "limit reached", "hit your limit", "out of extra usage",
               "лимит")
WEEK_STOP = 85


class Stop(Exception):
    pass


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower().replace("ё", "е"))).strip()


def run_ahead(n, text):
    """События из планов следующих глав, которые уже случились в главе n (с цитатой из главы)."""
    future = []
    for k in range(n + 1, len(BOOK["chapters"]) + 1):
        for s in BOOK["chapters"][k - 1]["scenes"]:
            future.append(f"гл.{k} «{s['title']}»: {s['what']}")
    if not future:
        return []
    own = "\n".join(f"«{s['title']}»: {s['what']}" for s in BOOK["chapters"][n - 1]["scenes"])
    known = BOOK["prep"]["characters"] + "\n\n" + BOOK["prep"]["world"]
    # Прошлые главы — тоже уже известно читателю: без них сторож на гл.13 принял за забегание то,
    # что Даша призналась ещё в гл.10
    past = "\n".join(f"гл.{k}: " + " ".join(s["what"] for s in BOOK["chapters"][k - 1]["scenes"]) for k in range(1, n))
    if past:
        known += "\n\nУЖЕ ПРОИЗОШЛО В ПРОШЛЫХ ГЛАВАХ (не забегание):\n" + past
    prompt = ("Ниже глава " + str(n) + " детектива, её план и планы СЛЕДУЮЩИХ глав. Найди, где "
              "глава " + str(n) + " ЗАБЕГАЕТ ВПЕРЁД — делает то, что по планам будет позже:\n"
              "- уже произошло событие из плана следующих глав (найдена улика, признание, задержание, "
              "открыт груз, найден человек);\n"
              "- раскрыто или названо то, что её план оставляет неизвестным, а планы следующих глав "
              "раскрывают позже: кто это был, чья вещь, кто виновен (например, план говорит «видел "
              "женщину», а в главе свидетель прямо называет её по имени).\n"
              "НЕ забегание: догадки и подозрения героини; намёки и улики, которые лишь указывают в "
              "сторону будущего, ничего не раскрывая (запись о лодке без огней — без имени, без вывода, "
              "кто и что возил) — честному детективу такие улики и нужны. Забегание — только когда "
              "читатель уже ЗНАЕТ то, что по плану узнаёт позже. Цитата — "
              "точная, 8–20 слов из главы.\n\n=== ПЛАН ЭТОЙ ГЛАВЫ ===\n" + own +
              "\n\n=== ИЗВЕСТНО С ПЕРВОЙ ГЛАВЫ (персонажи и мир — не забегание) ===\n" + known +
              "\n\n=== ПЛАНЫ СЛЕДУЮЩИХ ГЛАВ ===\n" + "\n".join(future) +
              f"\n\n=== ГЛАВА {n} ===\n" + text +
              '\n\nКаждой находке дай kind: «раскрытие» — читатель узнал то, что по плану узнаёт позже (кто это был, кто виновен, признание, найдена ключевая улика, случилось событие будущей главы); «деталь» — подробность из будущего плана появилась раньше, но ничего не раскрыла.' +
              '\n\nОтветь JSON без пояснений: {"happened": [{"chapter": 9, "scene": "…", "kind": "раскрытие", "quote": "…", "why": "…"}]}')
    code, r = fe("/api/inline_call", {"model": AHEAD_MODEL, "system": "Ты внимательный редактор. Только JSON.",
                                      "prompt": prompt, "max_tokens": 4000}, timeout=900)
    raw = (r or {}).get("result") or ""
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        items = json.loads(m.group(0)).get("happened", []) if m else []
    except Exception:
        log(f"  сторож забеганий: ответ не разобран: {raw[:200]}")
        return []
    t = _norm(text)
    ok = []
    for x in items:
        q = _norm(x.get("quote"))
        if len(q.split()) >= 4 and q in t:
            ok.append(x)
    return ok


def week_used():
    """(неделя %, окно %) подписки ChatGPT; не прочитать — (None, None) и запись в лог."""
    import subprocess
    code = ("import sys,os; os.environ['FE_CHATGPT_SUBSCRIPTION']='1'; sys.path.insert(0, " + repr(str(REPO / "fiction_engine")) + ");"
            "from engine.api import chatgpt_limits; l=chatgpt_limits(); print(l['secondary']['usedPercent'], l['primary']['usedPercent'])")
    err = ""
    for _ in range(3):
        try:
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                  encoding="utf-8", timeout=120)
        except subprocess.TimeoutExpired:
            err = "лимиты не ответили за 120 с"
            continue
        out = proc.stdout.split()
        if len(out) >= 2:
            return int(out[0]), int(out[1])
        err = (proc.stderr or proc.stdout).strip()[-300:]
        time.sleep(20)
    # Не прочитали — стоп по неделе не работает: сказать, а не молчать (разбор 21.10)
    log(f"ВНИМАНИЕ: лимиты ChatGPT не прочитаны — стоп на {WEEK_STOP}% недели не действует: {err}")
    return None, None


def check_limit_error(where, r):
    msg = json.dumps(r, ensure_ascii=False).lower()
    if any(w in msg for w in LIMIT_WORDS):
        raise Stop(f"{where}: похоже на лимит подписки — {msg[:300]}")


# ─── Привычки и логика ────────────────────────────────────────────────────────
# Привычка Sonnet по разборам Haiku и судьи на книге 18.10 — сравнения через
# «как…» («как человек, который…»). Счётчик движка (text_signals) видит только
# «словно / будто». Считаем в авторской речи на 1000 слов: черновик и финал.

def _narr(text):
    return "\n".join(l for l in text.splitlines() if l.strip() and not l.strip().startswith(("—", "–", "-")))


def habits(text):
    t = _narr(text)
    k = max(len(t.split()), 1) / 1000
    return {
        "words_narr": len(t.split()),
        "как_после_запятой": round(len(re.findall(r",\s+как\s+(?!будто|бы\b|только|раз\b|и\b|можно|нельзя|всегда|обычно)", t, re.I)) / k, 1),
        "как_человек_который": len(re.findall(r"\bкак\s+(?:человек|люди|те,\s+кто|тот,\s+кто)\b", t, re.I)),
        "словно_будто": round(len(re.findall(r"\b(?:словно|будто|точно\s+(?=[а-яё]+[,\s]))", t, re.I)) / k, 1),
        # Присказки и повторы («Фон», гл.1–3: «юридически говоря», «красная точка», «я не стала»)
        "повторы": _repeats(text),
    }


def _repeats(text):
    """Сочетания из двух слов (без служебных), которые повторяются в главе 4+ раз."""
    stop = set("и в во не на с со к по за из у о от до как это что он она они его её ее их я мы ты вы "
               "был была было были так но а же то ли бы уже ещё еще только когда если чтобы меня мне "
               "себя сказала сказал сказали".split())
    words = [w.lower().replace("ё", "е") for w in re.findall(r"[А-Яа-яЁё]+", text)]
    pairs = [(a, b) for a, b in zip(words, words[1:]) if a not in stop and b not in stop and len(a) > 3 and len(b) > 3]
    from collections import Counter
    return [f"{a} {b} ×{n}" for (a, b), n in Counter(pairs).most_common(5) if n >= 4]


def logic_check(n, text):
    """Выводы сыщика в главе и на что они опираются (проверяет модель другой семьи, чем писатель)."""
    before = "\n".join(f"гл.{k}: " + " ".join(s["what"] for s in BOOK["chapters"][k - 1]["scenes"])
                       for k in range(1, n))
    # Первая версия (гл.1–3) придиралась ко всему: 13 «частично» из 15, «солнце село в половине
    # пятого не доказано». Теперь — только выводы расследования и только натяжки, которые заметит
    # внимательный читатель детектива
    prompt = ("Ниже глава " + str(n) + " детектива и краткое содержание прошлых глав. Выпиши ВЫВОДЫ "
              "РАССЛЕДОВАНИЯ, которые делает сыщик (главный герой) в этой главе: где был человек, когда "
              "снят кадр, кто лжёт, кто что сделал, что из улики следует для дела. Не включай бытовые "
              "наблюдения, оценки характера, эмоции и догадки со словами «может быть». Знание героини о том, "
              "как устроены видео, город и сети, — допустимая опора, если она его называет. Для каждого вывода: "
              "на что он опирается. supported: «да» — опора показана читателю и вывод из неё разумно следует; "
              "«частично» — внимательный читатель детектива заметит натяжку: вывод заметно сильнее опоры; "
              "«нет» — опоры читатель не видел. Сомневаешься — «да». Цитата вывода — точная, 6–20 слов из главы.\n\n"
              "=== ПРОШЛЫЕ ГЛАВЫ ===\n" + (before or "—") + f"\n\n=== ГЛАВА {n} ===\n" + text +
              '\n\nОтветь JSON без пояснений: {"conclusions": [{"quote": "…", "basis": "…", "supported": "да", "why": "…"}]}')
    code, r = fe("/api/inline_call", {"model": CHECKER, "system": "Ты строгий редактор детективов. Только JSON.",
                                      "prompt": prompt, "max_tokens": 4000}, timeout=900)
    raw = (r or {}).get("result") or ""
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        items = json.loads(m.group(0)).get("conclusions", []) if m else []
    except Exception:
        return {"error": raw[:200]}
    t = _norm(text)
    for x in items:
        x["quote_ok"] = len(_norm(x.get("quote")).split()) >= 4 and _norm(x.get("quote")) in t
    return {"items": items,
            "count": {s: sum(1 for x in items if x.get("supported") == s and x["quote_ok"]) for s in ("да", "частично", "нет")}}


def active_ok():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    got = c.execute("select value from settings where key='active_project'").fetchone()
    return got and str(got[0]) == str(PID)


# ─── Глава ────────────────────────────────────────────────────────────────────

def chapter(n):
    ch = BOOK["chapters"][n - 1]
    rec = {"rounds": []}
    t0 = time.time()
    if not active_ok():
        raise Stop(f"гл.{n}: активный проект в FE — не «{BOOK['name']}» (id {PID}); не начинаю")
    ids, exp = planner_chapter(n, ch)
    rec["planner"] = {"scene_ids": ids, "export": {k: exp.get(k) for k in ("sent", "facts", "error", "message")}}
    log(f"гл.{n}: план из планировщика — {rec['planner']['export']}")
    if PLAIN:
        # Без кнопки и без своей задачи: глава идёт по плану из планировщика
        task = f"Напиши главу {n}."
    elif ASSIST or not ch.get("task"):
        # «🧠 Подготовить промт» → «← Вставить в поле задачи», без правки: задачу готовит приложение
        code, pa = fe("/api/prompt-assist", {"chapter_num": n, "model": ROLES["model_gen"]})
        if code != 200 or not pa.get("prompt"):
            check_limit_error(f"гл.{n} подготовка промта", pa)
            raise Stop(f"гл.{n}: «Подготовить промт» — {code} {str(pa)[:300]}")
        task = pa["prompt"]
        log(f"гл.{n}: задача от «Подготовить промт»:\n{task}")
    else:
        task = ch["task"] + "\n\nОбъём: " + BOOK.get("volume", "2800–3300 слов — в каждой из трёх сцен не меньше 900 слов.")
    rec["task"] = task
    code, pv = fe("/pipeline/preview", {"chapter_num": n, "task": task, "engine_mode": "quick",
                                        "model_gen": ROLES["model_gen"]})
    rec["prompt_chars"] = pv.get("chars")
    rec["prompt_has_plan"] = "СЦЕНА 1" in (pv.get("prompt") or "")
    code, r = fe("/pipeline/start", {"chapter_num": n, "generation_prompt": task, "engine_mode": "quick",
                                     "review": True, **ROLES})
    if code != 200 or not r.get("run_id"):
        check_limit_error(f"гл.{n} запуск", r)
        log(f"гл.{n}: ОШИБКА запуска {code} {str(r)[:300]}")
        rec["error"] = str(r)[:500]
        return rec
    run_id = r["run_id"]
    prompt = task
    cands = []             # (принята судьёй, балл, круг, текст) — принимаем лучший, а не последний
    for rnd in range(MAX_EXTRA + 1):
        text = r.get("generated_text") or ""
        if rnd == 0:
            rec["_habits_draft"] = habits(text)
        cands.append((r.get("verdict") == "ПРИНЯТЬ", float(r.get("judge_score") or r.get("score") or 0), rnd + 1, text))
        cont = r.get("continuity") or {}
        code, pc = fe("/pipeline/plan_check", {"chapter_num": n, "text": text, "run_id": run_id,
                                               "model_gen": ROLES["model_gen"]})
        items = pc.get("items") or []
        missing = [x for x in items if x["status"] in ("нет", "частично")]
        rec["rounds"].append({
            "round": rnd + 1, "words": len(text.split()), "verdict": r.get("verdict"),
            "judge_score": r.get("judge_score") or r.get("score"), "critic_score": r.get("critic_score"),
            "continuity": cont,
            "signals": (r.get("text_signals") or [])[:6], "warning": r.get("warning"),
            "edit_report": r.get("edit_report"),
            "app_ahead": pc.get("ahead"),          # сторож приложения (сверка с планом, #125)
            "plan": [(x["status"], x["item"].split("\n")[0], x["quote_ok"]) for x in items] or pc.get("error")})
        log(f"гл.{n} круг {rnd + 1}: {len(text.split())} слов, вердикт {r.get('verdict')}, "
            f"судья {r.get('judge_score') or r.get('score')}, план: "
            + (" ".join(x['status'] for x in items) if items else str(pc.get('error'))[:80])
            + (f" | редактура {r.get('edit_report')}" if r.get("edit_report") else ""))
        if rnd >= 1 and ((r.get("verdict") == "ПРИНЯТЬ" and not [x for x in missing if x["status"] == "нет"]) or rnd == MAX_EXTRA):
            break
        # «Изменить промпт для следующей итерации» + «Ещё круг редактуры»
        fix = "\n".join(f"- {x['item'].splitlines()[0]}: {x['note'] or 'нет в главе'}" for x in missing)
        prompt = task          # пункты плана редактору даёт сам движок (step_edit, 18.10)
        # Натяжки логики правкой задачи не лечились («Фон», гл.18–21: опора 55% → 47%, фильтр откатывал)
        code, r = fe("/pipeline/continue", {"run_id": run_id, "chapter_num": n, "generation_prompt": prompt,
                                            "previous_text": text, "previous_critique": r.get("critique") or ""})
        if code != 200:
            check_limit_error(f"гл.{n} круг", r)
            log(f"гл.{n}: ОШИБКА круга {code} {str(r)[:300]}")
            break
        r.setdefault("generated_text", text)
    # Лучший вариант по вердикту и баллу судьи; при равенстве — более поздний (правка обычно лучше).
    # Гл.10, 21, 22: черновик 32 «принять», после правки 29 — скрипт брал последний.
    # Выбирает приложение, как в окне «Принять»: при близком балле — круг с более полным планом
    best = max(cands, key=lambda c: (c[0], c[1], c[2])) if cands else None
    code, rr = fe(f"/pipeline/{run_id}/rounds")
    bt = next((x["text"].strip() for x in (rr.get("rounds") or []) if x["round"] == rr.get("best")), None) \
        if code == 200 else None
    app_best = next((c for c in cands if bt and c[3].strip() == bt), None)
    if app_best:
        best = app_best
    rec["app_best"] = app_best[2] if app_best else None
    final = best[3] if best and best[3] else (r.get("generated_text") or text)
    rec["accepted_round"] = best[2] if best else None
    if best and best[2] != len(cands):
        log(f"гл.{n}: принимаю круг {best[2]} (судья {best[1]}), а не последний ({cands[-1][1]})")
    (B / "chapters").mkdir(exist_ok=True)
    # Рабочие заметки писателя латиницей («Фон», гл.21) — движок ловит их с PR #119; здесь — страховка
    notes = [l for l in final.splitlines()
             if len(re.findall(r"[A-Za-z]{2,}", l)) >= 4 and len(re.findall(r"[A-Za-z]", l)) > len(re.findall(r"[А-Яа-яЁё]", l))]
    if len(notes) >= 2:
        (B / "chapters" / f"ch{n:02}-notes.txt").write_text(final, encoding="utf-8")
        raise Stop(f"гл.{n}: в главе рабочие заметки модели ({len(notes)} строк) — не принимаю, текст в ch{n:02}-notes.txt")
    if not active_ok():
        (B / "chapters" / f"ch{n:02}-unaccepted.txt").write_text(final, encoding="utf-8")
        raise Stop(f"гл.{n}: активный проект в FE сменился — глава не принята, текст в chapters/ch{n:02}-unaccepted.txt")
    rec["habits"] = {"черновик": rec.pop("_habits_draft", None), "финал": habits(final)}
    hd, hf = rec["habits"]["черновик"] or {}, rec["habits"]["финал"]
    log(f"гл.{n}: привычки «, как» {hd.get('как_после_запятой')}→{hf['как_после_запятой']}/1000, "
        f"«как человек, который» {hd.get('как_человек_который')}→{hf['как_человек_который']}, "
        f"словно/будто {hd.get('словно_будто')}→{hf['словно_будто']}/1000, повторы {hf['повторы']}")
    (B / "chapters" / f"ch{n:02}.txt").write_text(final, encoding="utf-8")
    code, acc = fe("/pipeline/accept", {"run_id": run_id, "chapter_num": n, "final_text": final,
                                        "model_value": ROLES["model_gen"]})
    log(f"гл.{n}: принята {code} {acc}")
    wait_after_accept(n, acc.get("state_job"))
    rec["minutes"] = round((time.time() - t0) / 60, 1)
    rec["run_id"] = run_id
    rec["after"] = snapshot(n)
    a = rec["after"]
    log(f"гл.{n}: State {a['state_chars']} симв., персонажи {len(a['characters'])}, дубли {a['dup_characters']}, "
        f"разделы-дубли {a['dup_sections']}, ГДЕ_СЕЙЧАС «{(a['where_now'] or '')[:80]}», L3 {a['l3']}, "
        f"библия {a['bible_rows']} (конфликтов {a['bible_conflicts']}), промпт {rec['prompt_chars']}")
    ahead = run_ahead(n, final)
    rec["run_ahead"] = ahead
    reveals = [x for x in ahead if "раскрыт" in str(x.get("kind", "")).lower()]
    for x in ahead:
        if x not in reveals:
            log(f"  деталь раньше плана (не стоп): гл.{x.get('chapter')} — {(x.get('why') or '')[:150]}")
    ahead = reveals
    if ahead and SMOKE:        # дымовая книга: забегание — в отчёт, прогон идёт дальше до отката и удаления
        log(f"гл.{n}: забегание вперёд (в отчёт) — " + "; ".join(x.get("why", "")[:120] for x in ahead))
    elif ahead:
        results["chapters"][str(n)] = rec; save()
        raise Stop(f"гл.{n}: забегание вперёд — " + "; ".join(f"гл.{x.get('chapter')} «{x.get('scene')}»: {x.get('why','')[:120]}" for x in ahead))
    log(f"гл.{n}: забеганий нет")
    if SMOKE:                  # дымовая книга ловит поломки движка, не качество — без логики и голоса
        return rec
    lc = logic_check(n, final)
    rec["logic"] = lc
    if lc.get("items") is not None:
        weak = [x for x in lc["items"] if x.get("supported") in ("нет", "частично") and x["quote_ok"]]
        log(f"гл.{n}: логика — выводов {len(lc['items'])}, опора {lc['count']}")
        for x in weak:
            log(f"  {x.get('supported')}: «{x.get('quote','')[:90]}» — {x.get('why','')[:140]}")
    else:
        log(f"гл.{n}: проверка логики не разобрана: {lc.get('error')}")
    # Голос — «Голос → Проверить» приложения (судья набора, другая семья, чем писатель)
    # Номер главы — эталон из глав до неё; писатель — проверяющий другой семьи
    code, vc = fe("/voice/check", {"text": final, "model": CHECKER, "chapter_num": n,
                                   "writer": ROLES["model_gen"]}, timeout=900)
    rec["voice"] = {"score": vc.get("score"), "analysis": vc.get("analysis") or vc.get("error")}
    nm = re.search(r"НЕ СОВПАДАЕТ:(.*?)(ИСПРАВИТЬ:|\Z)", rec["voice"]["analysis"] or "", re.S)
    log(f"гл.{n}: голос {vc.get('score')}/10 — " + " / ".join(
        l.strip("- ").strip()[:90] for l in (nm.group(1) if nm else "").strip().splitlines() if l.strip())[:300])
    return rec


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    last = int(sys.argv[2]) if len(sys.argv) > 2 else LAST
    planner_setup()
    try:
        for n in range(first, last + 1):
            if str(n) in results["chapters"] and results["chapters"][str(n)].get("after"):
                continue
            w, p = week_used()
            log(f"гл.{n}: ChatGPT неделя {w}%, окно {p}%")
            if w is not None and w >= WEEK_STOP:
                raise Stop(f"неделя ChatGPT {w}% — стоп до сброса")
            while p is not None and p >= 95:          # окно 5 ч почти кончилось — ждать сброса
                log(f"гл.{n}: окно ChatGPT {p}% — жду 10 мин")
                time.sleep(600)
                w, p = week_used()
            results["chapters"][str(n)] = chapter(n)
            save()
        log("готово")
    except Stop as e:
        log("СТОП: " + str(e))
        save()
        sys.exit(3)
