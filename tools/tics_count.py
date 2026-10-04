"""ИИ-обороты на 1000 слов: «не X, а Y», цепочки «…, и …, и …», «словно/будто/как будто»."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fiction_engine"))
from engine.pipeline_steps import find_and_chains

NOT_BUT = re.compile(r"\bне\s+[^.,!?—]{1,40},\s+а\s", re.I)
SIMILE = re.compile(r"\b(словно|будто|как будто|точно\s+(?=[а-яё]+\s))", re.I)

for path in sys.argv[1:]:
    chs = [c for c in json.load(open(path))["chapters"] if c["text"]]
    w = sum(len(c["text"].split()) for c in chs) / 1000
    nb = sum(len(NOT_BUT.findall(c["text"])) for c in chs)
    ch = sum(find_and_chains(c["text"])["count"] for c in chs)
    sm = sum(len(SIMILE.findall(c["text"])) for c in chs)
    print(f"{path.split('/')[-1]:22} «не X, а Y» {nb/w:5.2f}  цепочки «и…и» {ch/w:5.2f}  сравнения {sm/w:5.2f}  (на 1000 слов)")
