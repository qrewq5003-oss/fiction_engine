import json, re, sys
# Признаки пресетов голоса на 1000 слов авторской речи: без голоса → с пресетом.
# Запуск: python tools/voice_markers.py <scratchpad с mod16/ и voice7/>
S = sys.argv[1]
def narr(t):
    return "\n".join(l for l in t.splitlines() if l.strip() and not l.strip().startswith(("—", "–", "-")))
M = {
 "classic_detective_voice": ("«во-первых», вопросы в авторской речи", lambda n: len(re.findall(r"во-первых|во-вторых", n)) + n.count("?")),
 "psychological_detective_voice": ("«почему», «если бы я»", lambda n: len(re.findall(r"\bпочему\b|если бы я|на его месте", n))),
 "epic_fantasy_voice": ("века, поколения, предки, клятвы, обычаи", lambda n: len(re.findall(r"\bвек\w*|поколен\w*|предк\w*|клятв\w*|обыча\w*|\bрод\b|рода\b", n))),
 "dark_fantasy_voice": ("цена, плата", lambda n: len(re.findall(r"цен[аыуе]\b|плат[аиуы]\b|заплат\w*|расплат\w*", n))),
 "urban_fantasy_voice": ("быт города: метро, такси, телефон, кофе, счёт, аренда", lambda n: len(re.findall(r"метро|такси|телефон\w*|кофе|счёт|счета|аренд\w*|смен[аеуы]\b|начальник\w*", n))),
 "romance_voice": ("руки, голос, взгляд другого", lambda n: len(re.findall(r"(его|её|ее) (рук\w*|пальц\w*|голос\w*|взгляд\w*|губ\w*|плеч\w*|запах\w*)", n))),
 "scifi_voice": ("стоимость и обслуживание техники", lambda n: len(re.findall(r"стои\w*|цен[аыуе]\b|обслужива\w*|ремонт\w*|лиценз\w*|допуск\w*", n))),
 "realism_voice": ("повторяющееся время", lambda n: len(re.findall(r"\bбывало\b|по вечерам|по утрам|каждую|каждый|каждое|\bобычно\b|по субботам|по воскресеньям", n))),
 "noir_detective_voice": ("«я/меня/мне»", lambda n: len(re.findall(r"\b(я|меня|мне|мной)\b", n))),
}
GENRE = {"classic_detective_voice": "detective_classic", "psychological_detective_voice": "detective_classic",
         "epic_fantasy_voice": "fantasy_dark", "dark_fantasy_voice": "fantasy_dark",
         "urban_fantasy_voice": "realism_psychological", "romance_voice": "realism_psychological",
         "scifi_voice": "scifi_alt_history", "realism_voice": "realism_psychological"}
base = {}
for c in json.load(open(f"{S}/mod16/all16-full.json"))["chapters"] + json.load(open(f"{S}/voice7/base_althist.json"))["chapters"]:
    if c["text"] and (c["run"] < 2 or c["genre"] == "scifi_alt_history"):
        base.setdefault(c["genre"], []).append(c["text"])
def rate(texts, fn):
    w = sum(len(t.split()) for t in texts) / 1000
    return fn(" ".join(narr(t) for t in texts).lower()) / w
for v, g in GENRE.items():
    name, fn = M[v]
    ch = [c["text"] for c in json.load(open(f"{S}/voice7/{v}.json"))["chapters"] if c["text"]]
    print(f"{v:30} {g:22} {name:52} без голоса {rate(base[g], fn):5.2f} → с пресетом {rate(ch, fn):5.2f}")
