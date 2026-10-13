"""
Разметка находок `ab_compare series-check` судьёй: настоящее противоречие или нет.
Судья видит серию целиком и список находок, отвечает по каждой «да» / «нет».

    FE_CLAUDE_SUBSCRIPTION=1 python tools/adjudicate_cross.py check/check.json
пути — относительно .ab_work; серии — names/names.json, memory3/old.json, memory3/new.json
(замер 13.10, bench/ab-continuity-cross-2026-10-13.json).
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "fiction_engine"))
import ab_compare as ab
ab._temp_db(ROOT / "fiction_engine")
from engine.pipeline import _call
from engine.pipeline_llm import parse_json
D = ROOT / ".ab_work"
CHECK = sys.argv[1] if len(sys.argv) > 1 else "check/check.json"
rows = json.load(open(D/CHECK))["rows"]
series = {}
for f, in [("names/names.json",), ("memory3/old.json",), ("memory3/new.json",)]:
    d = json.load(open(D/f)); side = d.get("label") or Path(f).stem
    for s in d["series"]: series[(side, s["genre"], s["run"])] = s
P = """Ниже серия глав и список предполагаемых противоречий между главами. Для
каждого реши: это настоящая ошибка непрерывности (факт, заданный раньше,
нарушен позже без объяснения в тексте) — "да"; или нет — развитие сюжета,
раскрытие, ложь персонажа, которую текст так и подаёт, придирка — "нет".

{text}

=== ПРЕДПОЛАГАЕМЫЕ ПРОТИВОРЕЧИЯ ===
{items}

Ответь JSON без пояснений вокруг: {{"verdicts": [{{"id": 1, "real": "да"}}]}}"""
out = []
for key, s in series.items():
    found = [(r["checker"], f) for r in rows if (r["side"], r["genre"], r["run"]) == key and not r["failed"] for f in r["found"]]
    if not found: continue
    text = "=== ДО СЕРИИ ===\n" + ab.SEEDS[s["genre"]]["prev"] + "\n\n" + "\n\n".join(f"=== ГЛАВА {c['num']} ===\n{c['text']}" for c in s["chapters"])
    items = "\n".join(f"{i+1}. гл.{f['chapter_a']} «{f['quote_a']}» → гл.{f['chapter_b']} «{f['quote_b']}»: {f['what']}" for i, (_, f) in enumerate(found))
    try:
        v = parse_json(_call("claude_subscription::claude-sonnet-5-5", ab.RATE_SYSTEM, P.format(text=text, items=items), max_tokens=32000))
        ver = {int(x["id"]): str(x.get("real", "")).lower().startswith("да") for x in v["verdicts"]}
    except Exception as e:
        print("fail", key, repr(e)[:200]); continue
    for i, (cm, f) in enumerate(found):
        out.append({"key": list(key), "checker": cm, "real": ver.get(i + 1), **f})
    print(key, sum(1 for i in range(len(found)) if ver.get(i+1)), "/", len(found), flush=True)
json.dump(out, open(D/(CHECK.replace(".json", "-adj.json")), "w"), ensure_ascii=False, indent=1)
for cm in ("deepseek/deepseek-v4-pro-0813", "moonshotai/kimi-k2.5"):
    x = [o for o in out if o["checker"] == cm and o["real"] is not None]
    print(cm, "настоящих", sum(o["real"] for o in x), "из", len(x))
