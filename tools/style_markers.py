#!/usr/bin/env python3
"""
style_markers.py — меняют ли стили серии манеру текста.

Оценка судей говорит о качестве, а стиль отвечает за манеру. Здесь по
каждой главе считаются признаки манеры, и глава сравнивается со средним
набора базовых глав того же жанра (bench/base-pool-*.json): так жанр не
смешивается со стилем.

    python tools/style_markers.py bench/base-pool-2026-10-05.json bench/ab-styles-pool-2026-10-05.json
"""
import json
import re
import sys
from statistics import mean


def narration(text: str) -> str:
    return "\n".join(l for l in text.splitlines()
                     if l.strip() and not l.strip().startswith(("—", "–", "-")))


SENSORY = re.compile(r"\b(запах\w*|пахл\w*|пахн\w*|холод\w*|тепл\w*|звук\w*|шорох\w*|скрип\w*|"
                     r"свет\w*|тень|тени|сыр\w*|влажн\w*|шершав\w*|гул\w*|вкус\w*)\b")
INNER = re.compile(r"\b(думал\w*|подумал\w*|понимал\w*|понял\w*|чувствовал\w*|почувствовал\w*|"
                   r"знал\w*|вспомнил\w*|казалось|хотел\w*|боял\w*)\b")
SIMILE = re.compile(r"\b(словно|будто|как будто|точно)\b")


def markers(text: str) -> dict[str, float]:
    words = len(text.split()) or 1
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    dialog = sum(len(l.split()) for l in lines if l.startswith(("—", "–", "-")))
    sents = [s for s in re.split(r"[.!?…]+", text) if len(s.split()) > 0]
    nar = narration(text).lower()
    nw = len(nar.split()) or 1
    return {
        "диалог, %": 100 * dialog / words,
        "слов во фразе": mean(len(s.split()) for s in sents),
        "«я» на 1000": 1000 * len(re.findall(r"\b(я|меня|мне|мной)\b", nar)) / nw,
        "сенсорика на 1000": 1000 * len(SENSORY.findall(nar)) / nw,
        "внутр. мир на 1000": 1000 * len(INNER.findall(nar)) / nw,
        "сравнения на 1000": 1000 * len(SIMILE.findall(nar)) / nw,
    }


def main(pool_path: str, styles_path: str) -> None:
    pool = json.load(open(pool_path, encoding="utf-8"))
    base: dict[str, dict[str, float]] = {}
    for g in {c["genre"] for c in pool["chapters"]}:
        ms = [markers(c["text"]) for c in pool["chapters"] if c["genre"] == g]
        base[g] = {k: mean(m[k] for m in ms) for k in ms[0]}
    data = json.load(open(styles_path, encoding="utf-8"))
    keys = list(next(iter(base.values())))
    print(f"{'стиль':20}" + "".join(f"{k:>20}" for k in keys))
    print(f"{'база (среднее)':20}" + "".join(
        f"{mean(base[g][k] for g in base):>20.1f}" for k in keys))
    for style, chs in data["chapters"].items():
        rows = [(c["genre"], markers(c["text"])) for c in chs if c.get("text") and c["genre"] in base]
        if not rows:
            continue
        # Сдвиг относительно своего жанра, усреднённый по главам
        shift = {k: mean(m[k] - base[g][k] for g, m in rows) for k in keys}
        print(f"{style:20}" + "".join(f"{shift[k]:>+20.1f}" for k in keys))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
