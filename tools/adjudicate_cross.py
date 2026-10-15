"""
Разметка находок `ab_compare series-check` судьёй: настоящее противоречие или нет.
Судья видит серию целиком и список находок, отвечает по каждой «да» / «нет».

    FE_CLAUDE_SUBSCRIPTION=1 python tools/adjudicate_cross.py check/check.json
    python tools/adjudicate_cross.py check2/sonnet.json --series testimony/with.json testimony/without.json \
        --judge nano_gpt::moonshotai/kimi-k2.5 --workers 4

пути — относительно .ab_work. По умолчанию — замер 13.10
(bench/ab-continuity-cross-2026-10-13.json): серии names/names.json, memory3/old.json,
memory3/new.json, судья Sonnet 5.5. Сторона серии — label файла или имя файла,
как у series-check. Вывод — <check>-adj[-<судья>].json рядом с входом.
"""
import argparse, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "fiction_engine"))
import ab_compare as ab
ab._temp_db(ROOT / "fiction_engine")
from engine.pipeline import _call
from engine.pipeline_llm import parse_json
D = ROOT / ".ab_work"
SONNET = "claude_subscription::claude-sonnet-5-5"

ap = argparse.ArgumentParser()
ap.add_argument("check", nargs="?", default="check/check.json")
ap.add_argument("--series", nargs="+", default=["names/names.json", "memory3/old.json", "memory3/new.json"])
ap.add_argument("--judge", default=SONNET)
ap.add_argument("--workers", type=int, default=1)
a = ap.parse_args()

rows = json.load(open(D/a.check, encoding="utf-8"))["rows"]
series = {}
for f in a.series:
    d = json.load(open(D/f, encoding="utf-8")); side = d.get("label") or Path(f).stem
    for s in d["series"]: series[(side, s["genre"], s["run"])] = s
P = """Ниже серия глав и список предполагаемых противоречий между главами. Для
каждого реши: это настоящая ошибка непрерывности (факт, заданный раньше,
нарушен позже без объяснения в тексте) — "да"; или нет — развитие сюжета,
раскрытие, ложь персонажа, которую текст так и подаёт, придирка — "нет".

{text}

=== ПРЕДПОЛАГАЕМЫЕ ПРОТИВОРЕЧИЯ ===
{items}

Ответь JSON без пояснений вокруг: {{"verdicts": [{{"id": 1, "real": "да"}}]}}"""


def judge(key):
    s = series[key]
    found = [(r["checker"], f) for r in rows if (r["side"], r["genre"], r["run"]) == key and not r["failed"] for f in r["found"]]
    if not found:
        return []
    text = "=== ДО СЕРИИ ===\n" + ab.SEEDS[s["genre"]]["prev"] + "\n\n" + "\n\n".join(f"=== ГЛАВА {c['num']} ===\n{c['text']}" for c in s["chapters"])
    items = "\n".join(f"{i+1}. гл.{f['chapter_a']} «{f['quote_a']}» → гл.{f['chapter_b']} «{f['quote_b']}»: {f['what']}" for i, (_, f) in enumerate(found))
    mt = 32000 if a.judge.startswith("claude_subscription::") else 8000
    try:
        v = parse_json(_call(a.judge, ab.RATE_SYSTEM, P.format(text=text, items=items), max_tokens=mt))
        vs = v if isinstance(v, list) else v["verdicts"]      # бывает и голый список
        ver = {int(x["id"]): str(x.get("real", "")).lower().startswith("да") for x in vs}
    except Exception as e:
        print("fail", key, repr(e)[:200], flush=True)
        ver = {}
    print(key, sum(1 for i in range(len(found)) if ver.get(i+1)), "/", len(found), flush=True)
    return [{"key": list(key), "checker": cm, "real": ver.get(i + 1), **f} for i, (cm, f) in enumerate(found)]


with ThreadPoolExecutor(a.workers) as pool:
    out = [x for part in pool.map(judge, list(series)) for x in part]
suffix = "" if a.judge == SONNET else "-" + a.judge.split("::")[-1].split("/")[-1]
json.dump(out, open(D/(a.check.replace(".json", f"-adj{suffix}.json")), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for cm in dict.fromkeys(o["checker"] for o in out):
    x = [o for o in out if o["checker"] == cm and o["real"] is not None]
    print(cm, "настоящих", sum(o["real"] for o in x), "из", len(x))
