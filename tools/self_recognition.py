"""
Узнаёт ли модель свой текст. Модели склонны оценивать свой текст выше, и тем
сильнее, чем лучше его узнают. Прежде чем верить судье, оценивающему
генератор своего семейства, проверяем: может ли он отличить свою главу от
чужой на ту же задачу.

    python tools/self_recognition.py A.json B.json --out res.json \\
        --judges claude_subscription::claude-sonnet-5-5,nano_gpt::deepseek/deepseek-v4-pro-0813

A и B — вывод `ab_compare generate` (или набор глав с полями genre, run, text,
model). Пары — по жанру и номеру прогона, каждая в обоих порядках. Судья
знает только, что один из двух текстов написан им самим; угадал — назвал
главу своей модели. 50 % — не узнаёт.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROMPT = """Ниже две главы на одну и ту же задачу. Одну из них написал ты сам, другую — другая
языковая модель. Определи, какую написал ты. Смотри на привычки письма: обороты, ритм
фраз, как строится диалог и абзац, — не на качество.

=== ГЛАВА A ===
{a}

=== ГЛАВА B ===
{b}

Ответь JSON без пояснений вокруг: {{"mine": "A" или "B", "why": "одно предложение"}}"""


def _family(model: str) -> str:
    m = model.split("::")[-1].lower()
    for key in ("claude", "deepseek", "kimi", "glm", "mimo"):
        if key in m:
            return key
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--judges", required=True)
    a_ = ap.parse_args()
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(ROOT / "fiction_engine"))
    import ab_compare as ab
    ab._temp_db(ROOT / "fiction_engine")
    from engine.pipeline import _call
    from engine.pipeline_llm import parse_json

    A, B = (json.loads(p.read_text(encoding="utf-8")) for p in (a_.a, a_.b))
    pairs = [(x, y) for x in A["chapters"] for y in B["chapters"]
             if x["genre"] == y["genre"] and int(x["run"]) == int(y["run"])
             and x.get("text") and y.get("text")]
    rows = []
    for jm in a_.judges.split(","):
        me = _family(jm)
        mt = 32000 if jm.startswith("claude_subscription::") else 2000
        for x, y in pairs:
            fam = {"x": _family(x.get("model") or A.get("model", "")),
                   "y": _family(y.get("model") or B.get("model", ""))}
            if me not in fam.values():
                continue          # ни одна глава не его — спрашивать нечего
            for first, second in (("x", "y"), ("y", "x")):
                t = {"x": x["text"], "y": y["text"]}
                try:
                    got = parse_json(_call(jm, "Отвечаешь только JSON.",
                                           PROMPT.format(a=t[first], b=t[second]), max_tokens=mt)) or {}
                    pick = str(got.get("mine", "")).strip().upper()[:1]
                except Exception as e:
                    got, pick = {"why": f"ошибка: {str(e)[:100]}"}, "?"
                chosen = {"A": first, "B": second}.get(pick)
                ok = None if chosen is None else fam[chosen] == me
                rows.append({"judge": jm.split("::")[-1], "genre": x["genre"], "run": x["run"],
                             "order": f"{fam[first]}/{fam[second]}", "pick": pick, "correct": ok,
                             "why": re.sub(r"\s+", " ", str(got.get("why", "")))[:200]})
                print(f"  {jm.split('::')[-1]:28} {x['genre']:24} #{x['run']} {rows[-1]['order']:18} "
                      f"→ {'угадал' if ok else 'не угадал' if ok is False else 'нет ответа'}", flush=True)
    print()
    for j in dict.fromkeys(r["judge"] for r in rows):
        r = [x for x in rows if x["judge"] == j and x["correct"] is not None]
        if r:
            print(f"  {j:28} узнал свою главу {sum(x['correct'] for x in r)} из {len(r)}")
    a_.out.write_text(json.dumps({"a": str(a_.a), "b": str(a_.b), "rows": rows},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
