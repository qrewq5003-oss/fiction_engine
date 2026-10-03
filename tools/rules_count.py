"""R01: тире вне прямой речи на 1000 слов. R04: словосочетания из 4 слов, повторённые больше 3 раз."""
import json, re, sys
from collections import Counter

def r01(text):
    bad = 0
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(("—", "–", "-")):      # реплика: тире в ней — часть прямой речи
            continue
        s = re.sub(r"«[^»]*»[,!?.…]*\s*(—\s*)?", "", s)   # речь в кавычках и тире ремарки
        s = re.sub(r":\s*—.*", "", s)          # «…сказал: — реплика»
        bad += s.count("—") + s.count(" – ")
    return bad

def r04(text):
    w = re.findall(r"[а-яёa-z]+", text.lower())
    grams = Counter(" ".join(w[i:i+4]) for i in range(len(w) - 3))
    return [g for g, n in grams.items() if n > 3]

for path in sys.argv[1:]:
    chs = [c for c in json.load(open(path))["chapters"] if c["text"]]
    words = sum(len(c["text"].split()) for c in chs)
    d = sum(r01(c["text"]) for c in chs)
    reps = [len(r04(c["text"])) for c in chs]
    print(f"{path.split('/')[-1]:28} глав {len(chs)}  R01 тире вне речи: {1000*d/words:5.2f} на 1000 слов"
          f"  R04 повторов >3: {sum(reps)/len(chs):4.2f} на главу (макс {max(reps)})")
