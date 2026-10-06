"""Конкретные вопросы о романтической линии: различают ли судьи A и B."""
import json, random, sys
from pathlib import Path
from statistics import mean
from concurrent.futures import ThreadPoolExecutor
ROOT = Path("/home/deck/Downloads/fiction_engine")
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "fiction_engine"))
import ab_compare as ab
ab._temp_db(ROOT / "fiction_engine")
from engine.pipeline import _call
from engine.pipeline_llm import parse_json
# Каталог для глав и результатов: первый аргумент, по умолчанию .ab_work/secondary_line
D = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / ".ab_work/secondary_line")
D.mkdir(parents=True, exist_ok=True)
Q = ["Чувство показано через детали — что она замечает в нём, паузы, тело, — а не названо словами («влюблена», «любит»)",
     "Между ними есть напряжение или препятствие, которое мешает прямо сейчас",
     "Признание или влечение подготовлено предыдущими сценами, а не возникает внезапно",
     "Он — живой человек со своими целями и реакциями, а не функция сюжета",
     "Их разговоры несут подтекст: говорят об одном, слышат другое"]
P = """Ниже глава детектива с романтической линией. Ответь на вопросы только о романтической линии.
Оценка: 0 — нет, 1 — частично, 2 — да, явно. Сначала короткая цитата-доказательство, потом оценка.

{qs}

=== ГЛАВА ===
{text}

Ответь JSON без пояснений вокруг: {{"answers": [{{"q": 1, "quote": "…", "score": 0}}, …]}}"""
chs = [r for r in json.load(open(D / "rewritten.json")) if r["text"]]
qs = "\n".join(f"{i}. {q}" for i, q in enumerate(Q, 1))

def run(job):
    c, jm = job
    for _ in range(2):
        try:
            got = parse_json(_call(jm, "Ты строгий редактор. Отвечаешь только JSON.",
                                   P.format(qs=qs, text=c["text"]), max_tokens=3000)) or {}
            a = {int(x["q"]): float(x["score"]) for x in got.get("answers", [])}
            if len(a) == len(Q):
                return {"variant": c["variant"], "run": c["run"], "judge": jm.split("::")[-1], "scores": a}
        except Exception:
            pass
    return {"variant": c["variant"], "run": c["run"], "judge": jm.split("::")[-1], "scores": None}

jobs = [(c, jm) for c in chs for jm in ab.DEFAULT_JUDGES]
random.Random(3).shuffle(jobs)
rows = list(ThreadPoolExecutor(4).map(run, jobs))
json.dump(rows, open(D / "questions.json", "w"), ensure_ascii=False, indent=1)
ok = [r for r in rows if r["scores"]]
for i, q in enumerate(Q, 1):
    a = mean(r["scores"][i] for r in ok if r["variant"] == "A")
    b = mean(r["scores"][i] for r in ok if r["variant"] == "B")
    print(f"  A {a:.2f}  B {b:.2f}  {q[:70]}")
for v in "AB":
    print(f"  {v} сумма {mean(sum(r['scores'].values()) for r in ok if r['variant'] == v):.2f} из 10")
print("  не разобрано", len(rows) - len(ok))
