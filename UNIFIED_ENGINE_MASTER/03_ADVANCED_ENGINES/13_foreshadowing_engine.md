# 🎯 FORESHADOWING & PAYOFF ENGINE v1.0

**Модуль:** advanced_engines/13_foreshadowing_engine.md  
**Версия:** 1.0.0  
**Зависимости:** plot_points.json, character_resonance.md

---

## PROMPT:QUICK

<!-- Секции PROMPT:QUICK и PROMPT:FULL — ровно то, что движок отдаёт модели.
     QUICK идёт во всех режимах, FULL — дополнение для QUALITY и MASTER.
     Всё ниже них — справочник для автора, в промпт не попадает.
     Без код-блоков: они в промпт не идут. -->

**Ружьё Чехова:** что показано в начале, должно выстрелить позже. Не выстрелит — не показывай.

**Виды намёков:**
1. **Конкретный** — предмет, событие или фраза, которые вернутся.
2. **Атмосферный** — деталь задаёт ощущение (запах, звук, тишина, реакция животного): не предсказывает, а настраивает.
3. **Тематический** — мотив повторяется, и смысл его нарастает.
4. **Драматическая ирония** — читатель знает больше персонажа, и каждая сцена от этого тревожнее.
5. **Брошенная реплика** — сказанное мимоходом окажется важным.

**Дистанция:** конкретные детали возвращаются через несколько глав, отношения и убеждения — через 4–10, темы и образы — через всю книгу, первая сцена рифмуется с финальной. Раньше чем через 2–3 главы расплата выглядит механической.

**Правило на главу:** реши, что из этой главы будет использовано позже, и посей один намёк — органично, так, чтобы он работал и в своей сцене.

**Красный флаг:** если читатель понимает, что это намёк, в момент чтения, — слишком явно.

### Жанровые варианты предзнаменований

**ДЕТЕКТИВ:** Все улики честно показаны до раскрытия — это контракт жанра. Намёк — улика, которую читатель видит, но не связывает. Ложный след обязателен, иначе разгадка очевидна.

**ХОРРОР:** Атмосферные намёки важнее конкретных: деталь, которая «не так». Каждые 3–4 главы намёк становится явнее. Показать угрозу слишком быстро — потерять нагнетание.

**ФЭНТЕЗИ:** Пророчество намеренно двусмысленно и сбывается буквально или наоборот. Повторяющийся в мире символ, существо, место — тематический намёк.

**ТРИЛЛЕР:** Предателя выдают поведенческие сбои, а не прямые улики. После раскрытия каждую сцену с ним можно перечитать иначе. Рано — выдаёт, поздно — нечестно.

**РОМАНТИКА:** Будущий чёрный момент закладывается в первой трети — деталью, которая пока выглядит нейтральной.

**РЕАЛИЗМ:** Предвестие бытовое: привычка, оговорка, вещь, которую не выбрасывают, всплывает, когда становится важной. Никаких знамений: будущее видно в том, как персонажи уже сейчас обходят больную тему.

**НФ:** Предвестие — в правилах мира: ограничение технологии, названное рано и буднично, решает финал. Сбой, который все игнорируют, — будущая катастрофа. Решение не появляется из ниоткуда: всё, что спасёт героя, читатель уже видел.

## PROMPT:FULL

**Как сеять:**
- упоминай естественно, в контексте: деталь должна работать на текущую сцену, а не ждать своего часа;
- прячь важное среди обыденного описания;
- черта характера, мелькнувшая мимоходом (даже в шутку), позже становится препятствием в решающий момент;
- визуальная рифма: образ первой сцены возвращается в финале изменённым;
- сон или пророчество сбываются, но с поворотом.

**Как держать ружьё тёплым:** главное упоминается два-три раза до выстрела; небольшая роль до большой. Одно упоминание в середине абзаца на сотой странице читатель не вспомнит.

**Схемы расплаты:**
- одна большая — для ключевых поворотов;
- три касания — посев, отголосок, отголосок, выстрел; для главного оружия и главных откровений;
- нарастающая — мелкое применение, среднее, решающее; для навыков и отношений;
- ложная и настоящая — «а, это было просто…», а потом «нет, это было важно»; для загадок.

**Ошибки:**
- слишком явно: «это ещё пригодится», многозначительный взгляд на предмет без причины, целая сцена ради одной детали;
- слишком тонко: одно упоминание, которого никто не вспомнит;
- без расплаты: посеяно и забыто — читатель спросит «а что с…?»;
- навык или предмет появляется ровно тогда, когда нужен, без подготовки.

**Хорошая расплата** удивляет и при этом кажется неизбежной: «ну конечно!». Лучше двойная — сюжетная и эмоциональная сразу. Доверяй читателю: он замечает тонкое.

---

## 🎯 НАЗНАЧЕНИЕ

Система **намёков (foreshadowing)** и **расплат (payoffs)** — профессиональный инструмент для создания удовлетворяющих читателя историй, где всё имеет смысл в ретроспективе.

**"Chekhov's Gun: If you show a gun in Act 1, it must fire by Act 3. If it won't fire, don't show it."**

---

## 📊 ТИПЫ FORESHADOWING

### 1. CONCRETE (Конкретный)

**Прямой объект/событие, которое вернётся:**

```json
{
  "type": "concrete",
  "plant_location": "Ch3, page 47",
  "item": "Grandfather's hunting rifle over fireplace",
  "setup": "Character mentions it casually",
  "payoff_location": "Ch18, page 312",
  "payoff": "Used in climactic confrontation",
  "distance": "15 chapters",
  "strength": "HIGH"
}
```

**Правила:**
- Mention naturally (no spotlight)
- Distance: 3+ chapters minimum
- Payoff must feel inevitable yet surprising
- Multiple uses = stronger (mention in Ch3, Ch7, use in Ch18)

---

### 2. THEMATIC (Тематический)

**Идея/тема, которая получит развитие:**

```json
{
  "type": "thematic",
  "plant": "Ch2: 'Trust is a luxury we can't afford'",
  "theme": "Trust vs Survival",
  "development": [
    "Ch5: Protagonist betrayed by ally",
    "Ch9: Forced to trust enemy",
    "Ch15: Must choose: trust or survive"
  ],
  "payoff": "Ch20: Chooses trust, nearly dies, but wins",
  "arc": "Linear escalation"
}
```

---

### 3. DRAMATIC IRONY (Драматическая ирония)

**Читатель знает больше чем персонаж:**

```json
{
  "type": "dramatic_irony",
  "reader_knows": "Mentor is the traitor",
  "character_believes": "Mentor is trustworthy",
  "tension": "Every scene with mentor = anxiety",
  "payoff": "Ch16: Character discovers truth",
  "duration": "12 chapters of tension"
}
```

---

### 4. SYMBOLIC (Символический)

**Объект/образ с глубоким значением:**

```json
{
  "type": "symbolic",
  "symbol": "Broken mirror in protagonist's apartment",
  "first_mention": "Ch1",
  "meaning_layer_1": "Fractured self-image",
  "meaning_layer_2": "Bad luck",
  "evolution": [
    "Ch1: Ignores it",
    "Ch8: Looks at it, hates reflection",
    "Ch15: Considers fixing it",
    "Ch20: Finally replaces it (healing)"
  ],
  "payoff_type": "Character arc visualization"
}
```

---

### 5. ATMOSPHERIC (Атмосферный)

**Создание предчувствия:**

```json
{
  "type": "atmospheric",
  "setup": "Ch4: Crows gathering, unnatural silence",
  "mood": "Dread, foreboding",
  "payoff": "Ch7: Village attack",
  "technique": "Environmental cues",
  "reader_effect": "Vague unease → confirmed fear"
}
```

---

### 6. DIALOGUE HINT (Через диалог)

**Персонаж говорит что-то важное, кажется случайным:**

```
PLANT (Ch3):
— Worst way to die? Drowning. Happened to my brother.

PAYOFF (Ch14):
Protagonist nearly drowns, flashback to this conversation,
finds will to survive because of it.
```

---

## 🔫 CHEKHOV'S GUN TRACKER

### Система отслеживания "ружей":

```json
{
  "chekhov_guns": [
    {
      "gun_id": "gun_001",
      "item": "Poison in medicine cabinet",
      "introduced": "Ch2, page 23",
      "status": "LOADED (not fired yet)",
      "must_fire_by": "Ch20 (Act 3 climax)",
      "current_chapter": "Ch12",
      "warning": "⚠️ Midpoint passed, gun not fired",
      "suggestions": [
        "Fire in Ch15-17 (rising action)",
        "OR remove in revision (cut Ch2 mention)"
      ]
    },
    {
      "gun_id": "gun_002",
      "item": "Character's medical training",
      "introduced": "Ch1",
      "status": "✅ FIRED",
      "payoff": "Ch9: Saves ally's life",
      "satisfaction": "HIGH (good setup-payoff distance)"
    }
  ]
}
```

**RULES:**
- Every "gun" must fire OR be removed
- Distance: minimum 2 chapters, maximum 75% of book
- Multiple small payoffs > one big (compound interest)
- Failed payoff = reader frustration

---

## 📈 SETUP-PAYOFF PATTERNS

### PATTERN 1: SINGLE PAYOFF
```
Setup (Ch3) ────────────────────> Payoff (Ch18)
               15 chapters
               
GOOD FOR: Major plot points
```

### PATTERN 2: TRIPLE TAP
```
Setup (Ch3) ──> Echo (Ch8) ──> Echo (Ch14) ──> Payoff (Ch20)
                 
GOOD FOR: Main weapons, important reveals
EFFECT: Keeps gun "warm" in reader's mind
```

### PATTERN 3: ESCALATING PAYOFFS
```
Setup (Ch2) ──> Payoff 1 (Ch7) ──> Payoff 2 (Ch15) ──> Final (Ch22)
                 Minor use         Medium use          Major use
                 
GOOD FOR: Skills, relationships, recurring elements
EFFECT: Increasing satisfaction
```

### PATTERN 4: RED HERRING → REAL PAYOFF
```
Setup (Ch4) ──> False Payoff (Ch10) ──> Real Payoff (Ch19)
                "Oh it was just X"      "Wait, it WAS important!"
                
GOOD FOR: Mystery, misdirection
EFFECT: Surprise twist
```

---

## 🎭 PAYOFF STRENGTH CALCULATOR

```python
def calculate_payoff_strength(setup, payoff):
    score = 0
    
    # Distance (sweet spot: 5-12 chapters)
    distance = payoff.chapter - setup.chapter
    if 5 <= distance <= 12:
        score += 3
    elif 3 <= distance <= 15:
        score += 2
    else:
        score += 1
    
    # Emotional stakes
    if setup.emotional_weight == "HIGH":
        score += 3
    elif setup.emotional_weight == "MEDIUM":
        score += 2
    
    # Surprise factor
    if payoff.surprising and payoff.inevitable:
        score += 3  # "Oh! Of course!"
    elif payoff.inevitable:
        score += 2  # Satisfying but expected
    elif payoff.surprising:
        score += 1  # Surprising but feels random
    
    # Integration
    if payoff.integrates_multiple_setups:
        score += 2  # Multiple threads converge
    
    return interpret_score(score)

SCORE INTERPRETATION:
10-12: EXCELLENT payoff (reader satisfaction high)
7-9:   GOOD payoff (satisfying)
4-6:   WEAK payoff (meh)
0-3:   FAILED payoff (frustrating)
```

---

## 🔍 FORESHADOWING TECHNIQUES

### TECHNIQUE 1: BURY THE LEDE
**Hide important detail in mundane description:**

```
BAD (obvious):
"The knife gleamed on the table. It would be important later."

GOOD (buried):
"The kitchen was a mess—unwashed dishes, yesterday's newspaper, 
a knife someone left out. She'd clean it tomorrow."

→ Knife mentioned casually, no emphasis
→ Reader doesn't register it consciously
→ Subconscious notes it
→ Payoff feels organic
```

---

### TECHNIQUE 2: EARLY CHARACTER TRAIT → CRITICAL MOMENT

```
SETUP (Ch2):
Marcus mentions he's claustrophobic. Brief scene, played for humor.

PAYOFF (Ch16):
Climax happens in elevator. His claustrophobia becomes
major obstacle. Reader: "Oh shit, I remember!"
```

---

### TECHNIQUE 3: THROW-AWAY LINE → PLOT POINT

```
SETUP (Ch5):
"My dad always said, 'locks only keep honest people out.'"
— casual dialogue, seems like flavor

PAYOFF (Ch14):
Protagonist breaks into antagonist's house using this philosophy.
Remembers dad's words. Emotional + practical payoff.
```

---

### TECHNIQUE 4: VISUAL ECHO

```
SETUP (Ch1):
Opening image: Empty swing moving in the wind. Eerie.

PAYOFF (Ch24):
Final image: Child on swing, laughing. Same swing. Life returned.

EFFECT: Bookend + thematic closure
```

---

### TECHNIQUE 5: PROPHECY/DREAM

```
SETUP (Ch4):
Character has nightmare: drowning in darkness, can't breathe.

PAYOFF (Ch18):
Literally happens. But with twist—finds way out because
nightmare prepared them mentally.
```

---

## ⚠️ COMMON MISTAKES

### MISTAKE 1: TOO OBVIOUS
```
❌ "This will be important later."
❌ Character stares at object meaningfully for no reason
❌ Chapter devoted to single detail

✅ Natural mention in context
✅ Serves immediate scene purpose
✅ Feels organic
```

### MISTAKE 2: TOO SUBTLE
```
❌ Mentioned once, buried in page 47 paragraph 3
❌ No second mention before payoff
❌ Reader has zero chance of remembering

✅ Triple Tap pattern (mention 3 times)
✅ Give it small role before big role
```

### MISTAKE 3: NO PAYOFF
```
❌ Setup in Ch3, book ends, never paid off
❌ Reader: "What about the...?"

✅ Track all guns
✅ Fire or remove in revision
```

### MISTAKE 4: PAYOFF TOO EARLY
```
❌ Setup Ch2, Payoff Ch3 (1 chapter gap)
❌ No time for reader to forget
❌ Feels mechanical

✅ Minimum 3 chapter gap
✅ Optimal 5-12 chapters
```

### MISTAKE 5: DEUS EX MACHINA
```
❌ New skill/object appears exactly when needed
❌ No setup

✅ Setup skills/objects BEFORE crisis
✅ "Oh yeah, they mentioned they could..."
```

---

## 📋 FORESHADOWING CHECKLIST

**For each major plot point, ask:**

- [ ] Was it set up at least 3 chapters earlier?
- [ ] Did setup feel natural (not forced)?
- [ ] Was it mentioned 2-3 times (not just once)?
- [ ] Does payoff feel surprising YET inevitable?
- [ ] Does it serve emotional + plot purpose?
- [ ] Would reader slap forehead: "Of course!"?

**For each Chekhov's Gun:**

- [ ] Introduced early enough?
- [ ] Serves immediate scene purpose when introduced?
- [ ] Fired by Act 3?
- [ ] If not fired, removed in revision?

---

## 🎯 INTEGRATION WITH OTHER MODULES

**With Character Resonance:**
```
Foreshadowing character relationships.
Setup: Tension between A and B (Ch2)
Payoff: They must work together (Ch15)
```

**With Tension Curve:**
```
Foreshadowing raises tension.
Setup creates question → Tension until payoff
```

**With Reader Simulation:**
```
Track: Does reader remember the setup?
If reader forgot → strengthen setup OR shorten distance
```

**With Thematic DNA:**
```
Thematic foreshadowing reinforces themes.
Setup theme early → payoff at climax
```

---

## 📊 DIAGNOSTIC: BOOK SCAN

```python
def scan_foreshadowing(manuscript):
    """
    Scans entire manuscript for setup-payoff issues
    """
    issues = []
    
    # Find all setups
    setups = find_all_setups(manuscript)
    
    for setup in setups:
        # Check if paid off
        payoff = find_payoff(setup, manuscript)
        
        if not payoff:
            issues.append({
                "type": "UNFIRED_GUN",
                "location": setup.location,
                "item": setup.item,
                "severity": "HIGH",
                "fix": "Add payoff OR remove setup"
            })
        
        elif payoff.distance < 3:
            issues.append({
                "type": "TOO_CLOSE",
                "setup": setup.location,
                "payoff": payoff.location,
                "distance": f"{payoff.distance} chapters",
                "severity": "MEDIUM",
                "fix": "Increase distance or combine with another setup"
            })
        
        elif payoff.distance > 20:
            issues.append({
                "type": "TOO_FAR",
                "setup": setup.location,
                "payoff": payoff.location,
                "distance": f"{payoff.distance} chapters",
                "severity": "MEDIUM",
                "fix": "Add reminder/echo around midpoint"
            })
    
    return generate_report(issues)
```

---

## 🏆 EXAMPLES FROM MASTERS

**Harry Potter (J.K. Rowling):**
```
Setup: Sirius Black mentioned as betrayer (Book 3, early)
Echo: Multiple references, building dread
Payoff: Revealed Pettigrew was real betrayer
Effect: "Oh! The whole time!"
```

**Breaking Bad:**
```
Setup: Ricin cigarette (Season 2)
Echo: Referenced several times
Payoff: Used in finale (Season 5)
Distance: 3 SEASONS
Effect: Legendary payoff
```

**The Sixth Sense:**
```
Setup: Red objects throughout
Meaning: Unclear first viewing
Payoff: Rewatch reveals all red = dead interaction
Effect: Rewatch value
```

---

## ✅ FINAL RULES

1. **Setup everything important** — No deus ex machina
2. **Fire all guns** — Or remove them
3. **Distance matters** — 3-12 chapters optimal
4. **Bury naturally** — No spotlight on setup
5. **Triple tap major items** — Remind reader it exists
6. **Surprising + Inevitable** — Best payoffs
7. **Emotional + Plot** — Double payoff
8. **Trust the reader** — They're smart, pick up subtle cues

---

**ВЕРСИЯ:** 1.0  
**РАЗМЕР:** ~11 KB  

**"The best foreshadowing is invisible on first read, obvious on second."**
