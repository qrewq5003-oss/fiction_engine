"""
voice_drift.py — плавает ли голос по серии и меняют ли персонажи обращение.

Без вызовов моделей, по готовым сериям (`ab_compare series`).

1. Дрейф манеры: признаки `style_markers.markers` по главам серии. Разброс
   между главами серии сравнивается с разбросом между двумя половинами одной
   главы — это шум признака. Главы расходятся не сильнее половин — дрейфа нет.
   Отдельно — сдвиг от первой главы серии к последней (тренд).
2. Обращения: реплики, где персонажа зовут по имени, на «ты» или на «вы».
   Имя, к которому в серии обращаются и так и так, — кандидат на смену без
   повода; говорящего скрипт не знает, поэтому кандидаты печатаются с цитатами.

    python tools/voice_drift.py .ab_work/bible/sonnet-with.json .ab_work/testimony/with.json …
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fiction_engine"))
from style_markers import markers                      # noqa: E402
from engine.text_signals import _name_stem, _names     # noqa: E402

TY = re.compile(r"\b(ты|тебя|тебе|тобой|твой|твоя|твоё|твое|твои|твоего|твоей|твоих|твоим)\b", re.I)
VY = re.compile(r"\b(вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей|ваших|вашим)\b", re.I)
VERB_TY = re.compile(r"\b\w+(ешь|ишь|ёшь)\b", re.I)          # знаешь, видишь, идёшь


def halves(text: str) -> tuple[str, str]:
    paras = [p for p in text.split("\n") if p.strip()]
    mid = len(paras) // 2
    return "\n".join(paras[:mid]), "\n".join(paras[mid:])


def drift(series: list[dict]) -> dict:
    """По каждому признаку: разброс между главами, шум половин, тренд — в долях среднего."""
    keys = list(markers("а. б.").keys())
    between, noise, trend = defaultdict(list), defaultdict(list), defaultdict(list)
    for s in series:
        ms = [markers(c["text"]) for c in s["chapters"] if c.get("text")]
        if len(ms) < 2:
            continue
        for k in keys:
            vals = [m[k] for m in ms]
            mu = mean(vals) or 1e-9
            between[k].append(pstdev(vals) / abs(mu))
            trend[k].append((vals[-1] - vals[0]) / abs(mu))
        for c in s["chapters"]:
            a, b = halves(c.get("text") or "")
            if len(a.split()) < 300 or len(b.split()) < 300:
                continue
            ma, mb = markers(a), markers(b)
            for k in keys:
                mu = (ma[k] + mb[k]) / 2 or 1e-9
                # разброс двух точек pstdev = |a − b| / 2
                noise[k].append(abs(ma[k] - mb[k]) / 2 / abs(mu))
    return {k: {"между главами": mean(between[k]), "шум половин": mean(noise[k]),
                "тренд 1→N": mean(trend[k])} for k in keys if between[k] and noise[k]}


def addresses(series: list[dict]) -> list[dict]:
    """Имена, к которым в одной серии обращаются и на «ты», и на «вы»."""
    out = []
    for s in series:
        texts = [c.get("text") or "" for c in s["chapters"]]
        names = _names(texts)
        forms: dict[str, dict[str, list]] = defaultdict(lambda: {"ты": [], "вы": []})
        for ci, t in enumerate(texts):
            for line in t.splitlines():
                l = line.strip()
                if not l.startswith(("—", "–", "-")):
                    continue
                # реплика без слов автора: до первого « — » после начала
                speech = re.split(r"\s[—–]\s", l[1:], maxsplit=1)[0]
                for m in re.finditer(r"(?:^|[,!?.]\s*)([А-ЯЁ][а-яё]+)(?=\s*[,!?.])", speech):
                    w = m.group(1)
                    if w.lower() not in names:
                        continue
                    ty = bool(TY.search(speech) or VERB_TY.search(speech))
                    vy = bool(VY.search(speech))
                    if ty == vy:
                        continue          # нет местоимения или оба — не решаем
                    forms[_name_stem(w)]["ты" if ty else "вы"].append((s["chapters"][ci]["num"], w, speech[:110]))
        for stem, f in forms.items():
            if f["ты"] and f["вы"]:
                out.append({"серия": f"{s['genre']} #{s['run']}", "имя": f["ты"][0][1],
                            "ты": len(f["ты"]), "вы": len(f["вы"]),
                            "пример ты": f["ты"][0], "пример вы": f["вы"][0]})
    return out


def main(paths: list[str]) -> None:
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        series = [s for s in d["series"] if len(s.get("chapters", [])) >= 2]
        model = (d.get("model") or "?").split("::")[-1]
        print(f"\n=== {p}  ({model}, серий {len(series)}, глав {sum(len(s['chapters']) for s in series)})")
        for k, v in drift(series).items():
            ratio = v["между главами"] / (v["шум половин"] or 1e-9)
            print(f"  {k:20} между главами {100 * v['между главами']:5.1f} %  шум половин "
                  f"{100 * v['шум половин']:5.1f} %  отношение {ratio:4.2f}  тренд 1→N {100 * v['тренд 1→N']:+6.1f} %")
        ad = addresses(series)
        print(f"  обращения: имён и на «ты», и на «вы» — {len(ad)}")
        for a in ad:
            print(f"    {a['серия']} {a['имя']}: ты {a['ты']}, вы {a['вы']}\n"
                  f"      ты, гл.{a['пример ты'][0]}: {a['пример ты'][2]}\n"
                  f"      вы, гл.{a['пример вы'][0]}: {a['пример вы'][2]}")


if __name__ == "__main__":
    main(sys.argv[1:])
