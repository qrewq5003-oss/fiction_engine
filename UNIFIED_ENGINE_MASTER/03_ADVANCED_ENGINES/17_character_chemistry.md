# ⚗️ CHARACTER CHEMISTRY MATRIX v1.0

**Модуль:** advanced_engines/17_character_chemistry.md  
**Версия:** 1.0.0  
**Зависимости:** characters.json, relationships.json

---

## PROMPT:QUICK

<!-- Секции PROMPT:QUICK и PROMPT:FULL — ровно то, что движок отдаёт модели.
     QUICK идёт во всех режимах, FULL — дополнение для QUALITY и MASTER.
     Всё ниже них — справочник для автора, в промпт не попадает.
     Без код-блоков: они в промпт не идут. -->

**Химия — это притяжение, напряжение и дополняемость.** Не сходство, а черты, которые цепляются друг за друга: говорун и слушатель, планировщик и импровизатор, вспыльчивый и спокойный.

**Три источника напряжения:**
1. Противоположные ценности: долг и свобода, порядок и хаос.
2. Внешние препятствия: разный круг, запрет, время, обстоятельства.
3. Внутренний страх: один боится близости, другой — потери.

**Как химия видна на странице:**
- персонажи замечают конкретные, не клишейные детали друг друга;
- напряжение держится на том, что не сказано;
- юмор посреди серьёзного момента — признак близости;
- один меняет поведение, когда рядом второй, — и видно, как именно.

**Красный флаг:** если убрать второго персонажа из сцены и первый не изменится — химии нет.

**Правило на сцену:** реши, чего каждый хочет от другого в этой сцене, и пиши конфликт этих желаний.

### Жанровые варианты химии

**РОМАНТИКА:** Химия — главная линия, не украшение. Притяжение нарастает волнами. Каждая совместная сцена двигает к сближению или к конфликту, нейтральных нет. Физическое осознание — через конкретную деталь, а не абстрактное «она почувствовала».

**ДЕТЕКТИВ:** Между напарниками — профессиональное уважение и трение. Один видит то, что пропустил другой. Напряжение из разных методов, а не характеров. Доверие зарабатывается делом.

**ФЭНТЕЗИ/ПРИКЛЮЧЕНИЕ:** Химию проверяет опасность: кто кому доверяет жизнь и почему. Лояльность — главный маркер близости. Шутка в смертельной ситуации — высшая степень доверия.

**ТРИЛЛЕР:** Химия под давлением времени — быстрая и интенсивная, но с обратной стороной: союзник может предать. Близость и подозрение одновременно — читатель не знает, можно ли доверять.

**ХОРРОР:** Изоляция испытывает химию. Под страхом люди раскрываются: кто-то становится лучше, кто-то хуже. Предательство в группе выживших работает, потому что химия была настоящей.

**РЕАЛИЗМ:** Близость — в быту и общей истории: кто как наливает чай, кого не перебивают. Давние отношения держатся на невысказанном, и одна фраза сдвигает годы. Химия не обязана быть тёплой: раздражение — тоже связь.

**НФ:** Химию проверяют изоляция и зависимость: экипаж, отряд, выжившие — друг от друга не уйти. Доверие — кому отдаёшь доступ, коды, жизнеобеспечение. Связь с ИИ или машиной — настоящая, если у неё есть цена.

## PROMPT:FULL

**Типы связей и что их держит:**
- романтическая — что притягивает, что разводит, что сделает союз прочным; нужны все три;
- соперники — общая цель, противоположные методы, уважение, в котором не хотят признаваться; силы равны; путь от вражды к союзу;
- наставник и ученик — опыт в обмен на надежду и продолжение; ученик должен превзойти учителя, и в этом горечь;
- дружба без романтики — пережитое вместе, принятие без условий;
- токсичная — притяжение, разрушение и неспособность уйти.

**Что создаёт химию:** общий пережитый опыт, которого не понимает никто другой (связь сильная, но не всегда здоровая); взаимный вызов — один делает другого смелее, тот его — уязвимее; неудачное время — «если бы…».

**Приёмы показа:**
- синхронность: один бессознательно повторяет позу другого, замечает перемену в лице раньше слов;
- лёгкость в тишине: молчать вместе не неловко;
- непроизвольное внимание: знает, что второй рядом, раньше, чем видит, — через конкретную деталь, а не мурашки;
- защита: вступается за того, кого вроде бы не выносит, — «никто, кроме меня, не имеет права».

**От вражды к союзу — по ступеням:** вражда → вынужденная близость → неохотное уважение к умению → момент уязвимости → защита вопреки ссоре → доверие → дружба → верность. Ступени не перескакивают.

**Ошибки:**
- химию называют, а не показывают;
- любовь с первой главы без препятствий — отношения надо заработать;
- идеальная пара без трения — искры летят от столкновения;
- несовместимые базовые ценности сведены вместе без объяснения.

---

## 🎯 НАЗНАЧЕНИЕ

Алгоритм **химии между персонажами** — почему одни пары "щёлкают", а другие нет. Система для создания believable, dynamic relationships.

**"Chemistry isn't about similarity. It's about complementary dysfunction."**

---

## ⚡ CHEMISTRY TYPES

### 1. ROMANTIC CHEMISTRY

**Formula: Attraction + Tension + Compatibility**

```json
{
  "pair": "Character A + Character B",
  "attraction_factors": {
    "physical": 8,
    "intellectual": 9,
    "emotional": 6,
    "mysterious": 7
  },
  "tension_sources": [
    "Opposite values (A: duty, B: freedom)",
    "External obstacles (different social class)",
    "Internal fear (A: commitment-phobic)"
  ],
  "compatibility": {
    "shared_values": ["justice", "loyalty"],
    "complementary_traits": {
      "A_impulsive": "B_planning",
      "A_emotional": "B_logical"
    },
    "deal_breakers": "None identified"
  },
  "chemistry_score": 8.5
}
```

**KEY ELEMENTS:**
- **Initial spark** (what draws them together)
- **Sustained tension** (what keeps them apart)
- **Deep compatibility** (what makes it work long-term)

---

### 2. RIVALRY CHEMISTRY

**Formula: Similar Goals + Opposing Methods + Mutual Respect**

```json
{
  "rivals": "Detective A vs Detective B",
  "shared_goal": "Solve case",
  "conflict": "A: by the book, B: bend rules",
  "mutual_respect": "HIGH (hate to admit it)",
  "competitive_drive": "Both need to be best",
  "chemistry_type": "Enemies-to-allies potential"
}
```

**MAKES IT WORK:**
- They're evenly matched (no curb-stomp)
- Respect underneath animosity
- Learn from each other
- Potential arc: enemies → reluctant allies → friends

---

### 3. MENTOR-PROTÉGÉ CHEMISTRY

**Formula: Wisdom + Potential + Mutual Need**

```json
{
  "mentor": "Old warrior",
  "protégé": "Young recruit",
  "what_mentor_provides": "Experience, skills, perspective",
  "what_protégé_provides": "Hope, purpose, legacy",
  "tension": "Protégé must surpass mentor (bittersweet)",
  "chemistry_source": "Mutual redemption"
}
```

---

### 4. PLATONIC SOULMATES

**Formula: Understanding + History + No Romantic Tension**

```json
{
  "friends": "A & B",
  "bond": "Survived trauma together",
  "chemistry": "Finish each other's sentences",
  "why_not_romantic": "Like siblings, would feel wrong",
  "strength": "Unconditional acceptance"
}
```

---

### 5. TOXIC CHEMISTRY

**Formula: Attraction + Destruction + Inability to Leave**

```json
{
  "toxic_pair": "A + B",
  "attraction": "Intense physical/emotional",
  "destruction": [
    "Bring out worst in each other",
    "Cycles of hurt and makeup",
    "Sabotage each other's growth"
  ],
  "why_they_stay": "Addiction to intensity",
  "arc": "Must choose: break cycle or destroy selves"
}
```

---

## 🧪 CHEMISTRY FACTORS

### FACTOR 1: COMPLEMENTARY TRAITS

**Opposites attract (when complementary):**

| Character A | Character B | Chemistry |
|-------------|-------------|-----------|
| Talker | Listener | ✅ Good |
| Planner | Improviser | ✅ Good |
| Pessimist | Optimist | ✅ Good |
| Leader | Follower | ✅ Good |
| Hot-headed | Calm | ✅ Good |

**Opposites clash (when incompatible):**

| Character A | Character B | Chemistry |
|-------------|-------------|-----------|
| Pacifist | Violent | ❌ Conflict |
| Honest | Liar | ❌ No trust |
| Family-first | Selfish | ❌ Values clash |

---

### FACTOR 2: SHARED TRAUMA/EXPERIENCE

**Bonding through pain:**

```
FORMULA:
Survived same ordeal = instant understanding
Nobody else gets it = exclusive bond
Trauma creates chemistry (not always healthy)

EXAMPLE:
War veterans, abuse survivors, loss of same person
→ Deep connection
→ But: Can be codependent, prevent healing
```

---

### FACTOR 3: MUTUAL CHALLENGE

**They make each other better:**

```
CHARACTER A: Challenges B to be brave
CHARACTER B: Challenges A to be vulnerable

RESULT: Growth chemistry
They're better together than apart
```

---

### FACTOR 4: TIMING

**Right person, wrong time:**

```
HIGH CHEMISTRY but:
- One is married
- They're enemies
- Wrong life stage
- Geography

→ Creates delicious tension
→ "If only..." feeling
```

---

## 📊 CHEMISTRY DIAGNOSIS TOOL

```python
def calculate_chemistry(char_a, char_b, relationship_type):
    """
    Calculates chemistry score between two characters
    """
    score = 0
    
    # 1. Complementary traits (+3 points)
    if has_complementary_traits(char_a, char_b):
        score += 3
    
    # 2. Shared values (+2 points)
    shared = count_shared_values(char_a, char_b)
    score += min(shared, 2)
    
    # 3. Tension sources (+2 points)
    if has_romantic_obstacles(char_a, char_b):
        score += 2
    
    # 4. Mutual respect (+2 points)
    if respect_despite_conflict(char_a, char_b):
        score += 2
    
    # 5. Growth potential (+1 point)
    if they_challenge_each_other(char_a, char_b):
        score += 1
    
    # Penalties
    if incompatible_core_values(char_a, char_b):
        score -= 3
    
    if no_tension(char_a, char_b):
        score -= 2
    
    return {
        "score": score,
        "interpretation": interpret_score(score),
        "strengths": list_strengths(char_a, char_b),
        "weaknesses": list_weaknesses(char_a, char_b)
    }

SCORE INTERPRETATION:
8-10: ELECTRIC (undeniable chemistry)
6-7:  STRONG (believable, engaging)
4-5:  MODERATE (needs work)
2-3:  WEAK (forced, unconvincing)
0-1:  NONE (why are they together?)
```

---

## 💫 SHOWING CHEMISTRY

### TECHNIQUE 1: BODY LANGUAGE SYNC

```
NO CHEMISTRY:
They sat across from each other. She spoke. He listened.

CHEMISTRY:
She leaned in. He mirrored, unconsciously. When she 
laughed, his face softened. When he frowned, she noticed 
immediately.

→ Mirroring, attunement, awareness
```

---

### TECHNIQUE 2: BANTER FLOW

```
NO CHEMISTRY:
— How are you?
— Good. You?
— Good.

CHEMISTRY:
— You're late.
— You're early.
— Same thing.
— Not even close.
— [grins] Missed you too.

→ Rhythm, playfulness, understanding
```

---

### TECHNIQUE 3: COMFORTABLE SILENCE

```
NO CHEMISTRY:
Awkward silence. She searched for something to say.

CHEMISTRY:
They sat in silence. It wasn't awkward. It was... easy.
No need to fill the space. Being there was enough.

→ Ease, no performance needed
```

---

### TECHNIQUE 4: PHYSICAL AWARENESS

```
NO CHEMISTRY:
He was in the room. She noticed.

CHEMISTRY:
He entered and her skin prickled. Stupid body. 
Always knew when he was near before she saw him.
Gravitational pull or something.

→ Involuntary reactions, hyperawareness
```

---

### TECHNIQUE 5: DEFENDING THEM

```
NO CHEMISTRY:
Someone insults Character B. Character A shrugs.

CHEMISTRY:
Someone insults Character B.
Character A's jaw clenches. "Say that again."
Doesn't even like B. But nobody else gets to insult them.

→ Protective instinct
```

---

## 🔄 CHEMISTRY EVOLUTION

### ARC 1: STRANGERS → LOVERS

```
Stage 1: ATTRACTION (physical, instant)
Stage 2: INTEREST (who are you?)
Stage 3: OBSTACLE (can't have you)
Stage 4: TENSION (want you, fighting it)
Stage 5: BREAKING POINT (kiss/confession)
Stage 6: DEEPENING (beyond physical)
Stage 7: CONFLICT (differences emerge)
Stage 8: CHOICE (work or walk)
Stage 9: COMMITMENT (choosing each other)

EACH STAGE: Chemistry manifests differently
```

---

### ARC 2: ENEMIES → ALLIES

```
Stage 1: HATRED (genuine animosity)
Stage 2: FORCED PROXIMITY (must work together)
Stage 3: GRUDGING RESPECT (they're good at X)
Stage 4: VULNERABLE MOMENT (see past facade)
Stage 5: PROTECTION (defend despite feud)
Stage 6: TRUST (slowly earned)
Stage 7: FRIENDSHIP (unexpected)
Stage 8: LOYALTY (ride or die)

CHEMISTRY SHIFT: Hate → Respect → Trust → Bond
```

---

## ⚠️ CHEMISTRY MISTAKES

### MISTAKE 1: TOLD NOT SHOWN

```
❌ BAD:
"They had great chemistry."

✅ GOOD:
[Show through: banter, awareness, mirroring, tension]
```

---

### MISTAKE 2: INSTANT LOVE

```
❌ BAD:
Met in Ch1, in love by Ch2, no obstacles.

✅ GOOD:
Attraction in Ch1, obstacles through Act 2, 
earn the relationship.
```

---

### MISTAKE 3: NO CONFLICT

```
❌ BAD:
Perfect couple, agree on everything, no tension.

✅ GOOD:
Chemistry includes friction. Sparks fly from collision.
```

---

### MISTAKE 4: INCOMPATIBLE CORE VALUES

```
❌ BAD:
A: loves children, wants family
B: hates kids, never wants them
→ Forced together anyway

✅ GOOD:
Different but compatible values, OR address incompatibility
```

---

## 📋 CHEMISTRY CHECKLIST

**For each major relationship:**

- [ ] What draws them together? (Attraction factors)
- [ ] What keeps them apart? (Tension sources)
- [ ] What makes it work long-term? (Compatibility)
- [ ] Complementary or compatible traits?
- [ ] Shared values/experiences?
- [ ] Chemistry shown through action?
- [ ] Obstacles believable?
- [ ] Evolution arc planned?
- [ ] Reader can FEEL the chemistry?

---

## 🏆 EXAMPLES FROM MASTERS

**Pride & Prejudice:**
```
Elizabeth + Darcy
Chemistry: Banter, challenge, respect
Obstacles: Pride, prejudice, class
Why works: Grow past flaws together
```

**The Hating Game:**
```
Lucy + Josh
Chemistry: Rivalry, banter, sexual tension
Obstacles: Work enemies, competition
Why works: Matched equals, mutual respect
```

**Breaking Bad:**
```
Walt + Jesse
Chemistry: Mentor/protégé turned toxic
Bond: Mutual need, shared secrets
Arc: Codependence → destruction
```

---

**ВЕРСИЯ:** 1.0  
**РАЗМЕР:** ~9 KB  

**"Chemistry is that indefinable thing that makes readers ship it."**
