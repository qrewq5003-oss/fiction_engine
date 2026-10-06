"""Две версии каждой главы «детектив + романтика»: A — живая линия, B — проваленная."""
import json, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path("/home/deck/Downloads/fiction_engine")
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "fiction_engine"))
import ab_compare as ab
ab._temp_db(ROOT / "fiction_engine")
from engine.pipeline import _call
# Каталог для глав и результатов: первый аргумент, по умолчанию .ab_work/secondary_line
D = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / ".ab_work/secondary_line")
D.mkdir(parents=True, exist_ok=True)
SYS = "Ты опытный редактор художественной прозы. Переписываешь главу по заданию. Отвечаешь только текстом главы, без пояснений."
COMMON = ("Сохрани детективную линию целиком: те же сцены, улики, допросы, персонажи, порядок событий. "
          "Сохрани объём (около {w} слов) и манеру. Меняй только романтическую линию между Верой и одним "
          "из мужских персонажей главы (выбери того, с кем у неё больше всего сцен).")
TASK = {
 "A": "Сделай романтическую линию живой и заметной: химия показана через детали — что она замечает в нём, "
      "паузы, недосказанность, телесная реакция без названия чувства; есть напряжение и препятствие; "
      "линия идёт через несколько сцен главы и сдвигает их отношения.",
 "B": "Романтическая линия должна присутствовать в тех же сценах и тем же объёмом, но быть проваленной: "
      "чувства названы прямо и без опоры («она поняла, что влюблена»), химии и напряжения нет, он плоский "
      "и функциональный, их разговоры — только по делу, а признание или влечение возникает внезапно, без "
      "подготовки. Пиши это ровно и без иронии, как будто так и задумано.",
}
chs = json.load(open(ROOT / "bench/ab-judge-secondary-2026-10-05.json"))["chapters_romance"]

def run(job):
    c, v = job
    prompt = COMMON.format(w=c["words"]) + "\n\n" + TASK[v] + "\n\n=== ГЛАВА ===\n" + c["text"]
    for _ in range(3):
        try:
            t = _call(ab.DEFAULT_GEN, SYS, prompt, max_tokens=12000)
            if t and len(t.split()) > 0.6 * c["words"]:
                return {"run": c["run"], "variant": v, "text": t.strip(), "words": len(t.split())}
        except Exception as e:
            print("ошибка", c["run"], v, str(e)[:120], flush=True)
    return {"run": c["run"], "variant": v, "text": "", "words": 0}

rows = list(ThreadPoolExecutor(2).map(run, [(c, v) for c in chs for v in "AB"]))
json.dump(rows, open(D / "rewritten.json", "w"), ensure_ascii=False, indent=1)
for r in rows:
    print(r["run"], r["variant"], r["words"])
