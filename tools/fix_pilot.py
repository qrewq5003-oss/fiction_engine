"""
Пилот «проверка и точечная правка»: по находкам `ab_compare series-check`
писатель правит главу (`engine.continuity_fix`), проверяющий смотрит снова,
судья сравнивает прозу до и после. Четыре фазы, состояние — в одном JSON:

    python tools/fix_pilot.py fix     --out fix/sol61 --check check3/sol61-med.json \
        --series testimony/with.json testimony/without.json \
        --fixer nano_gpt::deepseek/deepseek-v4-pro-0813 --workers 4
    python tools/fix_pilot.py recheck --out fix/sol61 --checker chatgpt_subscription::gpt-6.1-sol@medium
    python tools/fix_pilot.py judge   --out fix/sol61 --judge chatgpt_subscription::gpt-6.1-sol@medium
    python tools/fix_pilot.py report  --out fix/sol61 \
        --adj check3/sol61-med-adj-kimi-k2.5.json check3/sol61-med-adj-claude-opus-5-5.json

Пути — относительно .ab_work. Главы правятся и перепроверяются против
ИСХОДНЫХ прошлых глав: так виден эффект самой правки, а не цепочки правок.
"""
import argparse, json, random, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "fiction_engine"))
import ab_compare as ab
ab._temp_db(ROOT / "fiction_engine")
from engine.pipeline import _call
from engine.continuity_checker import check_against_chapters
from engine.continuity_fix import changed_share, edits_summary, fix_contradictions
D = ROOT / ".ab_work"
FIX_SYSTEM = "Ты писатель этой серии. Правишь только указанные места. Отвечаешь только JSON."


def _mt(model: str, default: int) -> int:
    return 32000 if model.startswith("claude_subscription::") else default


def _state(out: Path) -> dict:
    return json.loads(out.read_text(encoding="utf-8"))


def _save(out: Path, st: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _prev_for(row: dict) -> list[dict]:
    """Прошлые главы до правимой: затравка серии + исходные главы по номеру."""
    return [{"number": ab.CHAPTER - 1, "content": ab.SEEDS[row["genre"]]["prev"]}] + \
           [{"number": c["num"], "content": c["text"]} for c in row["prev_chapters"]]


def phase_fix(a) -> None:
    rows_in = json.load(open(D / a.check, encoding="utf-8"))["rows"]
    series = {}
    for f in a.series:
        d = json.load(open(D / f, encoding="utf-8")); side = d.get("label") or Path(f).stem
        for s in d["series"]:
            series[(side, s["genre"], s["run"])] = s
    rows = []
    for r in rows_in:
        if r.get("failed") or not r["found"]:
            continue
        s = series[(r["side"], r["genre"], r["run"])]
        ch = next(c for c in s["chapters"] if c["num"] == r["chapter"])
        rows.append({"side": r["side"], "genre": r["genre"], "run": r["run"], "chapter": r["chapter"],
                     "task": ch.get("task", ""), "text_before": ch["text"],
                     "prev_chapters": [c for c in s["chapters"] if c["num"] < r["chapter"]],
                     "found_before": r["found"]})

    def run(row):
        try:
            res = fix_contradictions(row["chapter"], row["text_before"], row["found_before"],
                                     _prev_for(row),
                                     lambda p: _call(a.fixer, FIX_SYSTEM, p, max_tokens=_mt(a.fixer, 8000)))
            row.update(text_after=res["text"], edits=res["edits"], applied=res["applied"],
                       failed=res["failed"], fix_failed=False,
                       changed=changed_share(row["text_before"], res["text"]))
            note = edits_summary(res) + f", изменено {row['changed'] * 100:.1f} % слов"
        except Exception as e:
            row.update(text_after=row["text_before"], edits=[], applied=[], failed=[],
                       fix_failed=True, changed=0.0)
            note = f"сбой: {str(e)[:80]}"
        print(f"  {row['side']:8} #{row['run']} гл.{row['chapter']} находок {len(row['found_before'])}: {note}",
              flush=True)
        return row

    with ThreadPoolExecutor(a.workers) as pool:
        rows = list(pool.map(run, rows))
    st = {"date": date.today().isoformat(), "check": a.check, "series": a.series,
          "fixer": a.fixer, "rows": rows}
    _save(D / f"{a.out}.json", st)
    ok = [r for r in rows if not r["fix_failed"]]
    print(f"\n  глав {len(ok)}/{len(rows)}, замен {sum(len(r['applied']) for r in ok)} "
          f"из {sum(len(r['edits']) for r in ok)}, изменено в среднем "
          f"{100 * sum(r['changed'] for r in ok) / max(1, len(ok)):.1f} % слов")


def phase_reapply(a) -> None:
    """Наложить сохранённые замены заново (после правки сопоставления), без вызова модели."""
    from engine.continuity_fix import apply_edits
    out = D / f"{a.out}.json"; st = _state(out)
    for row in st["rows"]:
        if row["fix_failed"]:
            continue
        text, applied, failed = apply_edits(row["text_before"], row["edits"])
        row.update(text_after=text, applied=applied, failed=failed,
                   changed=changed_share(row["text_before"], text))
        for k in ("found_after", "remained", "new", "votes", "recheck_failed"):
            row.pop(k, None)
    st.pop("checker", None); st.pop("judge", None)
    _save(out, st)
    ok = [r for r in st["rows"] if not r["fix_failed"]]
    ways = {}
    for r in ok:
        for e in r["applied"]:
            ways[e["way"]] = ways.get(e["way"], 0) + 1
        for e in r["failed"]:
            ways[e["why"]] = ways.get(e["why"], 0) + 1
    print(f"  замен {sum(len(r['applied']) for r in ok)} из {sum(len(r['edits']) for r in ok)}: {ways}; "
          f"изменено в среднем {100 * sum(r['changed'] for r in ok) / max(1, len(ok)):.1f} % слов")


def phase_recheck(a) -> None:
    out = D / f"{a.out}.json"; st = _state(out)
    st["checker"] = a.checker

    def run(row):
        if row["fix_failed"] or row["text_after"] == row["text_before"]:
            row["found_after"] = row["found_before"]; row["recheck_failed"] = False
            return row
        try:
            row["found_after"] = [dict(f, chapter_b=row["chapter"]) for f in check_against_chapters(
                row["chapter"], row["text_after"], _prev_for(row),
                lambda p: _call(a.checker, ab.RATE_SYSTEM, p, max_tokens=_mt(a.checker, 4000)))]
            row["recheck_failed"] = False
        except Exception as e:
            row["found_after"] = []; row["recheck_failed"] = True
            print(f"  сбой проверки: {str(e)[:80]}", flush=True)
        before = [dict(f, chapter_b=row["chapter"]) for f in row["found_before"]]
        row["remained"] = [f for f in before if any(ab._same_finding(g, f) for g in row["found_after"])]
        row["new"] = [g for g in row["found_after"] if not any(ab._same_finding(g, f) for f in before)]
        print(f"  {row['side']:8} #{row['run']} гл.{row['chapter']} было {len(before)} → "
              f"осталось {len(row['remained'])}, новых {len(row['new'])}", flush=True)
        return row

    with ThreadPoolExecutor(a.workers) as pool:
        st["rows"] = list(pool.map(run, st["rows"]))
    _save(out, st)


def phase_selfcheck(a) -> None:
    """Правленая глава против самой себя (проверяющий), затем второй проход правщика по этим находкам."""
    from engine.continuity_checker import check_self_contradictions
    out = D / f"{a.out}.json"; st = _state(out)
    st["selfchecker"] = a.checker; st["fixer2"] = a.fixer

    def run(row):
        if row["fix_failed"] or row["text_after"] == row["text_before"]:
            row["self_found"] = []; return row
        try:
            row["self_found"] = check_self_contradictions(
                row["chapter"], row["text_after"],
                lambda p: _call(a.checker, ab.RATE_SYSTEM, p, max_tokens=_mt(a.checker, 4000)))
        except Exception as e:
            row["self_found"] = []; print(f"  сбой проверки: {str(e)[:80]}", flush=True)
        row["text_after1"] = row["text_after"]
        if row["self_found"]:
            try:
                res = fix_contradictions(row["chapter"], row["text_after"], row["self_found"],
                                         [{"number": row["chapter"], "content": row["text_after"]}],
                                         lambda p: _call(a.fixer, FIX_SYSTEM, p, max_tokens=_mt(a.fixer, 8000)))
                row.update(text_after=res["text"], edits2=res["edits"], applied2=res["applied"],
                           failed2=res["failed"], changed=changed_share(row["text_before"], res["text"]))
            except Exception as e:
                print(f"  сбой правки: {str(e)[:80]}", flush=True)
        print(f"  {row['side']:8} #{row['run']} гл.{row['chapter']} внутренних {len(row['self_found'])}, "
              f"замен {len(row.get('applied2', []))}, изменено всего {row['changed'] * 100:.1f} %", flush=True)
        return row

    with ThreadPoolExecutor(a.workers) as pool:
        st["rows"] = list(pool.map(run, st["rows"]))
    for r in st["rows"]:
        for k in ("found_after", "remained", "new", "votes", "recheck_failed"):
            r.pop(k, None)
    st.pop("checker", None); st.pop("judge", None)
    _save(out, st)
    print(f"\n  внутренних противоречий найдено {sum(len(r['self_found']) for r in st['rows'])}, "
          f"глав с ними {sum(1 for r in st['rows'] if r['self_found'])}")


def phase_judge(a) -> None:
    out = D / f"{a.out}.json"; st = _state(out)
    st["judge"] = a.judge
    rng = random.Random(20261015)

    def run(row):
        if row["fix_failed"] or row["text_after"] == row["text_before"]:
            row["votes"] = []; return row
        seed = ab.SEEDS[row["genre"]]
        orders = [("before", "after"), ("after", "before")]; rng.shuffle(orders)
        votes = []
        for first, second in orders:
            texts = {"before": row["text_before"], "after": row["text_after"]}
            prompt = ab.JUDGE_PROMPT.format(genre=seed["genre"], task=row["task"] or seed["task"],
                                            a=texts[first], b=texts[second])
            try:
                v = ab._parse_verdict(_call(a.judge, ab.JUDGE_SYSTEM, prompt, max_tokens=_mt(a.judge, 600)))
            except Exception as e:
                v = {"winner": "?", "margin": "", "reason": f"ошибка: {str(e)[:120]}"}
            who = {"A": first, "B": second, "tie": "tie"}.get(v.get("winner"), "?")
            votes.append({"order": f"{first}/{second}", "winner": who,
                          "margin": v.get("margin", ""), "reason": v.get("reason", "")})
        row["votes"] = votes
        w = [v["winner"] for v in votes]
        print(f"  {row['side']:8} #{row['run']} гл.{row['chapter']} {w[0]} / {w[1]}", flush=True)
        return row

    with ThreadPoolExecutor(a.workers) as pool:
        st["rows"] = list(pool.map(run, st["rows"]))
    _save(out, st)


def phase_report(a) -> None:
    st = _state(D / f"{a.out}.json"); rows = st["rows"]
    real = {}
    for f in a.adj:
        for x in json.load(open(D / f, encoding="utf-8")):
            k = (tuple(x["key"]), x["chapter_b"], x["quote_b"])
            real.setdefault(k, []).append(x["real"])
    def cls(row, f):
        v = real.get(((row["side"], row["genre"], row["run"]), row["chapter"], f["quote_b"]), [])
        return "настоящее" if v and all(v) else "спорное" if any(v) else "ложное" if v else "без разметки"
    ok = [r for r in rows if not r["fix_failed"]]
    print(f"правка: {st['fixer']}; глав {len(ok)} из {len(rows)}; замен "
          f"{sum(len(r['applied']) for r in ok)} из {sum(len(r['edits']) for r in ok)}; "
          f"изменено слов в среднем {100 * sum(r['changed'] for r in ok) / max(1, len(ok)):.1f} %")
    if "checker" in st:
        tot = {}; rem = {}
        for r in ok:
            for f in r["found_before"]:
                c = cls(r, f); tot[c] = tot.get(c, 0) + 1
                rem[c] = rem.get(c, 0) + any(ab._same_finding(dict(f, chapter_b=r["chapter"]), g)
                                             for g in r.get("found_after", []))
        n_new = sum(len(r.get("new", [])) for r in ok)
        print(f"перепроверка {st['checker']}: находок было {sum(tot.values())} → осталось "
              f"{sum(rem.values())}, новых {n_new}")
        for c in tot:
            print(f"  {c:12} было {tot[c]:3} → осталось {rem[c]}")
    if "judge" in st:
        s = {"after": 0, "before": 0, "tie": 0, "unstable": 0}
        for r in ok:
            w = [v["winner"] for v in r.get("votes", [])]
            if len(w) == 2 and w[0] == w[1] and w[0] in s:
                s[w[0]] += 1
            elif w:
                s["unstable"] += 1
        print(f"судья {st['judge']}: устойчиво за «после» {s['after']}, за «до» {s['before']}, "
              f"ничья {s['tie']}, зависит от порядка {s['unstable']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=("fix", "reapply", "selfcheck", "recheck", "judge", "report"))
    ap.add_argument("--out", default="fix/sol61")
    ap.add_argument("--check", default="check3/sol61-med.json")
    ap.add_argument("--series", nargs="+", default=["testimony/with.json", "testimony/without.json"])
    ap.add_argument("--fixer", default="nano_gpt::deepseek/deepseek-v4-pro-0813")
    ap.add_argument("--checker", default="chatgpt_subscription::gpt-6.1-sol@medium")
    ap.add_argument("--judge", default="chatgpt_subscription::gpt-6.1-sol@medium")
    ap.add_argument("--adj", nargs="*", default=["check3/sol61-med-adj-kimi-k2.5.json",
                                                 "check3/sol61-med-adj-claude-opus-5-5.json"])
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    {"fix": phase_fix, "reapply": phase_reapply, "selfcheck": phase_selfcheck,
     "recheck": phase_recheck, "judge": phase_judge, "report": phase_report}[a.phase](a)
