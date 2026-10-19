"""Калибровка порога «ПРИНЯТЬ» под судью: живые главы против испорченных.

    python tools/calib_judge.py JUDGE_MODEL EXCLUDE_FAMILY OUT.json

Окружение: CALIB_CRITIC — критик (по умолчанию Haiku 5.5, как CRITIC_MODEL движка),
CALIB_NO_CRITIC=1 — судья без разбора, CALIB_PICK=0/1 — выборка глав, CALIB_LIMIT — сколько.
Калибровки 16–19.10 — bench/judges-*, critic-no-nano-*, judge-repeat-*.

Как в Pipeline: критик → судья (step_critique, step_judge движка),
временная база с ключами (рабочая только читается). Живые — 12 глав
(4 жанра × 3 семьи, кроме семьи судьи), испорченные — те же главы, каждая
одной порчей: перемешаны абзацы / обратный порядок / продублирован кусок.
Перед каждым вызовом судьи по подписке ChatGPT — лимит.
"""
import datetime, json, random, re, sys, time
from pathlib import Path
import os
# Подписки включаются флагами окружения (в приложении — из .env): без них
# судья по подписке отказывал, и калибровка 16.10 прошла вхолостую
os.environ.setdefault("FE_CHATGPT_SUBSCRIPTION", "1")
os.environ.setdefault("FE_CLAUDE_SUBSCRIPTION", "1")
os.environ.setdefault("PYTHONUTF8", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "fiction_engine"))
import ab_compare  # noqa: E402
ab_compare._temp_db(ROOT / "fiction_engine")

from engine.db import create_project                       # noqa: E402
from engine.db_narrative import create_pipeline_run        # noqa: E402
from engine.pipeline import _call                          # noqa: E402
from engine.pipeline_steps import step_critique, step_judge  # noqa: E402

JUDGE, EXCLUDE, OUT = sys.argv[1], sys.argv[2], Path(sys.argv[3])
CRITIC = os.environ.get("CALIB_CRITIC", "claude_subscription::claude-haiku-5-5")
GENRES = ["detective_classic", "realism_psychological", "thriller_psychological", "fantasy_dark"]

ws = json.loads((ROOT / "bench/ab-writers-sonnet-2026-10-13.json").read_text(encoding="utf-8"))
wg = json.loads((ROOT / "bench/ab-writers-gpt61-2026-10-15.json").read_text(encoding="utf-8"))
SOURCES = {"claude": ws["chapters_sonnet"], "deepseek": ws["chapters_deepseek"],
           "kimi": ws["chapters_kimi"], "gpt": wg["chapters_gpt"]}
fams = [f for f in ("claude", "gpt", "deepseek", "kimi") if f != EXCLUDE][:3]
real = []
for fam in fams:
    for g in GENRES:
        # CALIB_PICK — какая по счёту глава жанра (0 — первая): добор новых глав
        pick = int(os.environ.get("CALIB_PICK", "0"))
        ch = [c for c in SOURCES[fam] if c.get("genre") == g and (c.get("text") or "").strip()][pick]
        real.append({"family": fam, "genre": g, "text": ch["text"]})


def paras(t):
    return [p for p in re.split(r"\n\s*\n", t.strip()) if p.strip()]


def spoil(t, kind, seed):
    p = paras(t)
    if kind == "shuffle":
        random.Random(seed).shuffle(p)
    elif kind == "reverse":
        p = p[::-1]
    else:                                    # дубль: середина главы ещё раз
        a, b = len(p) * 2 // 5, len(p) * 3 // 5
        p = p[:b] + p[a:b] + p[b:]
    return "\n\n".join(p)


KINDS = ["shuffle", "reverse", "duplicate"]
items = [{**r, "kind": "real"} for r in real] + \
        [{**r, "kind": KINDS[(i + int(os.environ.get("CALIB_PICK", "0"))) % 3], "text": spoil(r["text"], KINDS[(i + int(os.environ.get("CALIB_PICK", "0"))) % 3], 1016 + i)} for i, r in enumerate(real)]
random.Random(20261016).shuffle(items)       # вперемешку: живые и испорченные не блоками


def gate():
    if not JUDGE.startswith("chatgpt_subscription"):
        return
    from engine.api import chatgpt_limits
    while True:
        l = chatgpt_limits()
        if not l or not l.get("primary") or not l.get("secondary"):
            return                           # окно не открыто или лимиты не читаются — вызов сам скажет о лимите
        p, w = l["primary"]["usedPercent"], l["secondary"]["usedPercent"]
        if w >= 60:
            raise SystemExit(f"СТОП: неделя {w}%")
        if p < 88:
            return
        until = datetime.datetime.fromtimestamp(l["primary"]["resetsAt"]) + datetime.timedelta(minutes=2)
        print(f"окно {p}% — жду до {until:%H:%M}", flush=True)
        while datetime.datetime.now() < until:
            time.sleep(60)


def call(model, system, user, max_tokens=None, prefill=""):
    return _call(model, system, user, max_tokens=max_tokens or 3000, prefill=prefill)


CRIT = re.compile(r"(ГОЛОС|СТРУКТУРА|ПЕРСОНАЖИ|СЦЕНЫ|ДИАЛОГ)\s*:\s*\[?(\d+(?:[.,]\d+)?)")
pid = create_project("Калибровка", "калибровка")
done = [d for d in (json.loads(OUT.read_text(encoding="utf-8"))["items"] if OUT.exists() else [])
        if not d.get("error")]          # с ошибкой — перепроверить
import os
for n, it in enumerate(items[:int(os.environ.get("CALIB_LIMIT", "999"))]):
    key = (it["family"], it["genre"], it["kind"])
    if any((d["family"], d["genre"], d["kind"]) == key for d in done):
        continue
    gate()
    run = create_pipeline_run(pid, 1, CRITIC, CRITIC, CRITIC, JUDGE)
    res = {"generated_text": it["text"]}
    t0 = time.time()
    try:
        if os.environ.get("CALIB_NO_CRITIC"):
            # Опыт 18.10: судья без отдельного критика — разбора нет, оценивает сам
            res["critique"] = "(отдельного разбора нет — оцени главу сам)"
        else:
            step_critique(run, 1, 1, CRITIC, call, res, genre=it["genre"])
        if os.environ.get("CALIB_HIDE_SCORE") and not os.environ.get("CALIB_NO_CRITIC"):
            # Опыт: судья видит разбор критика без его баллов
            crit = re.sub(r"(?m)^\s*(ГОЛОС|СТРУКТУРА|ПЕРСОНАЖИ|СЦЕНЫ|ДИАЛОГ)\s*:\s*\[?\d+(?:[.,]\d+)?\]?\s*(?:/\s*10)?\s*[—–-]?\s*",
                          r"\1: ", res.get("critique", ""))
            res["critique"] = re.sub(r"(?m)^\s*ИТОГ\s*:.*$", "", crit)
            res["critique"] = re.sub(r"\d+(?:[.,]\d+)?\s*/\s*(?:50|10)", "", res["critique"])
        step_judge(run, 1, 1, JUDGE, call, res, genre_key=it["genre"])
        crit = {k: float(v.replace(",", ".")) for k, v in CRIT.findall(res.get("judgment", ""))}
        rec = {"family": it["family"], "genre": it["genre"], "kind": it["kind"],
               "critic_score": res.get("critic_score"), "judge_score": res.get("judge_score"),
               "criteria": crit, "verdict": res.get("verdict"), "seconds": round(time.time() - t0)}
    except Exception as e:
        rec = {"family": it["family"], "genre": it["genre"], "kind": it["kind"], "error": repr(e)[:300]}
    done.append(rec)
    print(n + 1, "/", len(items), rec, flush=True)
    OUT.write_text(json.dumps({"date": str(datetime.date.today()), "judge": JUDGE, "critic": CRITIC,
                               "items": done}, ensure_ascii=False, indent=1), encoding="utf-8")

ok = [d for d in done if d.get("judge_score") is not None]
print("\nпорог  живые проходят  испорченные протекают  (и критерий ≥ 4)")
for th in range(26, 45):
    def passes(d):
        return d["judge_score"] >= th and all(v >= 4 for v in d["criteria"].values())
    r = [d for d in ok if d["kind"] == "real"]; s = [d for d in ok if d["kind"] != "real"]
    print(f"{th:5}  {sum(map(passes, r)):3} из {len(r):2}        {sum(map(passes, s)):3} из {len(s):2}")
