# 📈 STAKES ESCALATION TRACKER v1.0

**Модуль:** advanced_engines/20_stakes_escalation.md  
**Версия:** 1.0.0  
**Рейтинг:** 5+/5  
**Зависимости:** tension_curve.md, plot_points.json

---

## 🎯 НАЗНАЧЕНИЕ

Система отслеживания и **эскалации ставок** — что персонаж может потерять. Low stakes = low investment. Stakes должны РАСТИ.

**"Stakes answer one question: Why should I care?"**

---

## 📊 4 TYPES OF STAKES

### 1. PERSONAL STAKES (Личные)

**What character will personally lose:**

```
EXAMPLES:
- Life (death)
- Freedom (prison, capture)
- Identity (who they are)
- Sanity
- Loved one
- Dream/goal
- Reputation

LEVEL SCALE:
1-3:  Minor inconvenience
4-6:  Significant loss
7-9:  Life-changing loss
10:   Everything
```

---

### 2. EXTERNAL STAKES (Внешние)

**What world/others will lose:**

```
EXAMPLES:
- City destroyed
- War
- Genocide
- Plague
- Environmental catastrophe
- Society collapse

DANGER: "Save the world" = abstract
FIX: Make it personal too (save world AND loved one)
```

---

### 3. EMOTIONAL STAKES (Эмоциональные)

**Relationships at risk:**

```
EXAMPLES:
- Lose love
- Betray friend
- Family fracture
- Trust destroyed
- Become monster (what you hate)

POWER: Often more compelling than life/death
```

---

### 4. MORAL STAKES (Моральные)

**Soul/principles at risk:**

```
EXAMPLES:
- Compromise values to win
- Become villain to defeat villain
- Sacrifice innocent to save many
- Lose humanity

DEPTH: Adds philosophical weight
```

---

## 📈 ESCALATION PATTERNS

### PATTERN 1: LINEAR (Steady Climb)

```
STAKES PROGRESSION:

Ch1:  Solve case (professional stakes)     [3/10]
Ch5:  + Job on the line                    [5/10]
Ch10: + Partner in danger                  [7/10]
Ch15: + Protagonist is suspect             [9/10]
Ch20: + Real killer will strike tonight    [10/10]

EFFECT: Steady pressure increase
USE: Mystery, thriller, procedural
```

---

### PATTERN 2: EXPONENTIAL (Accelerating)

```
STAKES PROGRESSION:

Ch1:  Find missing person                  [2/10]
Ch4:  Person is murdered                   [4/10]
Ch8:  Serial killer (more victims)         [7/10]
Ch14: Protagonist's family targeted        [10/10]

EFFECT: Rapid escalation, breathless
USE: Thriller, horror
```

---

### PATTERN 3: PLATEAU WITH SPIKES

```
STAKES PROGRESSION:

Ch1-5:   Medium stakes, steady             [5/10]
Ch6-10:  SPIKE to high                     [9/10]
Ch11-14: Back to medium (catch breath)     [5/10]
Ch15-20: SPIKE to maximum                  [10/10]

EFFECT: Rhythm, breathing room
USE: Longer books, series
```

---

### PATTERN 4: FALSE RELIEF (Deceptive)

```
STAKES PROGRESSION:

Ch1-8:   Stakes rising                     [8/10]
Ch9-11:  Seem to drop (victory?)           [4/10]
Ch12:    SPIKE higher than ever            [10/10]

EFFECT: Rug pull, devastating
USE: When you want to hurt reader
```

---

## 🎯 LAYERING STAKES

**Multiple stake types = stronger:**

### SINGLE LAYER (Weak):
```
Ch1-20: Save the city [External only]

PROBLEM: Abstract, hard to care
```

### TRIPLE LAYER (Strong):
```
Personal:  Protagonist will die if fails
External:  City will be destroyed
Emotional: Loved one is in city
Moral:     Must compromise values to win

RESULT: Reader cares on multiple levels
```

---

## 📊 STAKES LEVEL TRACKER

```json
{
  "chapter_stakes": [
    {
      "chapter": 1,
      "personal": 3,
      "external": 2,
      "emotional": 1,
      "moral": 0,
      "total": 6,
      "description": "Missing person case, professional"
    },
    {
      "chapter": 5,
      "personal": 5,
      "external": 4,
      "emotional": 4,
      "moral": 2,
      "total": 15,
      "description": "Multiple victims, partner endangered, 
                      job on line, moral compromise considered"
    },
    {
      "chapter": 10,
      "personal": 7,
      "external": 6,
      "emotional": 8,
      "moral": 5,
      "total": 26,
      "description": "Protagonist suspect, loved one kidnapped,
                      city in danger, must break rules to save"
    },
    {
      "chapter": 20,
      "personal": 10,
      "external": 10,
      "emotional": 10,
      "moral": 8,
      "total": 38,
      "description": "All stakes maximum, everything on line"
    }
  ]
}
```

---

## 🔧 ESCALATION TECHNIQUES

### TECHNIQUE 1: ADD LAYERS

**Start simple, add complexity:**

```
CHAPTER 1:
Just find the artifact. (External)

CHAPTER 5:
Find artifact + it's cursed (External + Personal)

CHAPTER 10:
Find artifact + cursed + cult wants it + friend possessed
(External + Personal + Emotional + Moral)
```

---

### TECHNIQUE 2: NARROW TIME FRAME

**Less time = higher stakes:**

```
WEEK 1:  Find killer before they strike again
         (Vague "again" = medium stakes)

DAY 1:   Find killer in 24 hours or victim dies
         (Specific deadline = high stakes)

HOUR 1:  Bomb detonates in 60 minutes
         (Ticking clock = maximum stakes)
```

---

### TECHNIQUE 3: MAKE IT PERSONAL

**Abstract → Specific:**

```
WEAK:
"Millions will die." (Abstract, hard to visualize)

STRONG:
"Your daughter is in that building. It explodes in 10 minutes."
(Personal, immediate, visual)
```

---

### TECHNIQUE 4: POINT OF NO RETURN

**Can't undo this:**

```
REVERSIBLE (lower stakes):
"If you fail, you'll be fired."
(Can find another job)

IRREVERSIBLE (higher stakes):
"If you fail, she dies."
(Can't undo death)
```

---

### TECHNIQUE 5: EVERYTHING AT ONCE

**Convergence of all threats:**

```
CLIMAX STAKES:
- Protagonist will die (personal)
- City will fall (external)
- Loved one betrayed them (emotional)
- Must kill innocent to win (moral)

ALL STAKES ACTIVE SIMULTANEOUSLY = MAXIMUM PRESSURE
```

---

## ⚠️ STAKES MISTAKES

### MISTAKE 1: STATIC STAKES

```
❌ BAD:
Ch1:  Defeat villain [5/10]
Ch10: Defeat villain [5/10]
Ch20: Defeat villain [5/10]

→ No escalation, boring

✅ GOOD:
Ch1:  Defeat villain [5/10]
Ch10: Villain has hostage [8/10]
Ch20: Villain has protagonist's family + bomb [10/10]

→ Escalating, gripping
```

---

### MISTAKE 2: TOO HIGH TOO EARLY

```
❌ BAD:
Ch1: World will end in 24 hours! Maximum stakes!

PROBLEM: Nowhere to escalate. Stays at 10/10.

✅ GOOD:
Ch1:  City threatened [6/10]
Ch10: Region threatened [8/10]
Ch20: World threatened [10/10]

→ Room to grow
```

---

### MISTAKE 3: ONLY EXTERNAL

```
❌ BAD:
"Save the world" (abstract, impersonal)

✅ GOOD:
"Save the world + your daughter is in it"
(Personal + External)
```

---

### MISTAKE 4: NO STAKES

```
❌ BAD:
Character has nothing to lose. Immortal. Alone.
No relationships. Doesn't care about anything.

PROBLEM: Why should reader care?

✅ GOOD:
Even immortal character needs stakes.
Give them: purpose, relationship, vulnerability, goal
```

---

### MISTAKE 5: UNCLEAR STAKES

```
❌ BAD:
"Things will be bad if you fail."

VAGUE. Reader doesn't know what's at risk.

✅ GOOD:
"If you fail: your sister dies, the cure is lost,
and the plague spreads. You have 6 hours."

SPECIFIC. Crystal clear consequences.
```

---

## 📊 STAKES DIAGNOSIS

```python
def diagnose_stakes(manuscript):
    """
    Analyzes stakes progression throughout book
    """
    chapters = split_into_chapters(manuscript)
    
    stakes_map = []
    for chapter in chapters:
        level = calculate_stakes_level(chapter)
        stakes_map.append(level)
    
    # Analyze pattern
    issues = []
    
    # Check for escalation
    if not is_escalating(stakes_map):
        issues.append({
            "type": "STATIC_STAKES",
            "severity": "HIGH",
            "description": "Stakes don't increase",
            "fix": "Raise stakes every act"
        })
    
    # Check for plateau
    if has_long_plateau(stakes_map, threshold=5):
        issues.append({
            "type": "STAKES_PLATEAU",
            "severity": "MEDIUM",
            "location": find_plateau(stakes_map),
            "fix": "Add complication or raise personal stakes"
        })
    
    # Check starting level
    if stakes_map[0] > 7:
        issues.append({
            "type": "TOO_HIGH_TOO_EARLY",
            "severity": "MEDIUM",
            "fix": "Lower initial stakes, give room to escalate"
        })
    
    return generate_stakes_report(stakes_map, issues)
```

---

## 📈 IDEAL STAKES CURVE

```
STAKES LEVEL
 10|                          *CLIMAX
   |                        **
  8|                   ****
   |              *****
  6|         *****
   |    ****         
  4| ***                          *RESOLUTION
   |*________________________________
     Act 1      Act 2        Act 3

PATTERN:
- Start moderate (3-5)
- Steady rise Act 1 (5-7)
- Spike Act 2 midpoint (7-8)
- Escalate Act 3 (8-10)
- Peak at climax (10)
- Drop resolution (3-4)
```

---

## ✅ STAKES CHECKLIST

**For each act:**

- [ ] Stakes clearly defined?
- [ ] Stakes higher than previous act?
- [ ] Multiple stake types present?
- [ ] Personal stakes included?
- [ ] Stakes specific (not vague)?
- [ ] Consequences clear?
- [ ] Ticking clock present?
- [ ] Irreversible if fail?
- [ ] Reader cares?

**For climax:**

- [ ] ALL stakes active?
- [ ] Maximum level reached?
- [ ] Personal + External + Emotional?
- [ ] No higher to go?

---

**ВЕРСИЯ:** 1.0  
**РАЗМЕР:** ~9 KB  
**УРОВЕНЬ:** 5+/5 Professional  
**СТАТУС:** ✅ PRODUCTION READY

**"Stakes are why we care. Escalation is why we can't stop reading."**

---

## ## MINI (QUICK режим — суть за 10 строк)

**Ставки отвечают на вопрос: почему мне важно?** Низкие ставки = низкая вовлечённость.

**Четыре типа ставок (от слабых к сильным):**
1. Физические: жизнь, свобода, здоровье.
2. Эмоциональные: отношения, любовь, принятие.
3. Социальные: репутация, место в обществе, семья.
4. Экзистенциальные: идентичность, смысл, душа.

**Правило эскалации:** ставки должны РАСТИ. Не только внешние — внутренние тоже.
Начало арки → личные ставки. Середина → социальные добавляются. Финал → экзистенциальные.

**Как поднять ставки без войны:**
- Персонаж узнаёт что потеряет если не действует (конкретно)
- Кто-то важный под угрозой из-за действий протагониста
- Таймер: время ограничено

**Правило на главу:** назови конкретно что персонаж потеряет если эта глава пойдёт не так. Расплывчато = низкие ставки.

### Жанровые варианты ставок

**ТРИЛЛЕР:** Ставки физические с самого начала. Эскалация = таймер сжимается. Ключевое: персонаж теряет ресурсы с каждой главой — информацию, союзников, время. Экзистенциальные ставки появляются только в финале.

**ХОРРОР:** Ставки начинаются с психологического — потеря контроля над реальностью, недоверие к себе. Физическая угроза подтверждает то что читатель уже чувствует. Ошибка — физические ставки без психологических: это экшн, не хоррор.

**РОМАНТИКА:** Ставки = будущее отношений. Физических нет (или они второстепенны). Эскалация через недопонимание, внешние обстоятельства, внутренние страхи. Чёрный момент = потеря возможности HEA — максимальные ставки жанра.

**ДЕТЕКТИВ:** Ставки = правда и справедливость, а не жизнь детектива. Личные ставки появляются когда расследование затрагивает самого детектива. Ошибка — ставки слишком рано становятся личными: теряется жанровая специфика.

**РЕАЛИЗМ:** Ставки малые внешне — огромные внутренне. Выбор профессии = выбор идентичности. Разговор с матерью = ставки отношений на всю жизнь. Читатель должен чувствовать вес без авторских объяснений.
