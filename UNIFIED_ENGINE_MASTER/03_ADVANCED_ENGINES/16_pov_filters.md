# 👁️ POV PERCEPTION FILTERS v1.0

**Модуль:** advanced_engines/16_pov_filters.md  
**Версия:** 1.0.0  
**Зависимости:** pov.md, deep_character_psychology.md

---

## PROMPT:QUICK

<!-- Секции PROMPT:QUICK и PROMPT:FULL — ровно то, что движок отдаёт модели.
     QUICK идёт во всех режимах, FULL — дополнение для QUALITY и MASTER.
     Всё ниже них — справочник для автора, в промпт не попадает.
     Без код-блоков: они в промпт не идут. -->

**Фильтр восприятия: один факт — разные реальности.** Персонаж видит не мир, а свою версию мира. Входит человек и улыбается: параноик видит фальшь и ищет, что ему нужно; влюблённый — что комната стала светлее; подавленный едва замечает, что кто-то вошёл.

**Ключевые фильтры:**
- страх — угроза везде, выходы, опасные детали;
- влюблённость — всё, что связано с человеком, остальное размыто;
- гнев — несправедливость на виду, нейтральное читается как враждебное;
- вина — свои ошибки увеличены, достижения уменьшены;
- паранойя — совпадений нет, у всего есть умысел;
- горе — мир продолжается как ни в чём не бывало, всё напоминает о потере;
- эйфория — риски преуменьшены, всё возможно;
- профессиональный — видит то, что связано с его ремеслом, остальное в фоне.

**Правило:** фильтр искажает восприятие фокального персонажа, а читатель видит больше, чем персонаж понимает.

### Жанровые варианты фильтров

**ДЕТЕКТИВ:** Фильтр сыщика профессиональный — замечает то, что пропускают другие. Но не всё: иначе раскрытие нечестно. Слепые пятна у него личные, а не профессиональные.

**ТРИЛЛЕР:** Под угрозой — туннельное зрение: детали угрозы крупно, остальное размыто. Несколько фокалов показывают одно событие кусками, картину собирает читатель.

**ХОРРОР:** Ненадёжный рассказчик: читатель видит больше героя — или меньше, если тот теряет связь с реальностью. Главный вопрос: можно ли верить тому, что он видит?

**РОМАНТИКА:** Два фокала — два прочтения одной сцены: для одного дружеская улыбка, для другого знак равнодушия. Напряжение — в несовпадении.

**РЕАЛИЗМ:** Обычный человек видит ограниченно: не замечает важного, замечает привычное. Финал может быть очевиден читателю и так и не стать очевидным герою.

**ФЭНТЕЗИ:** Фокал смотрит на мир как местный: привычное чудо его не удивляет, удивляет чужое ему самому. Объяснять мир законно глазами чужака, местному — нет. Предрассудки его народа решают, кого он видит врагом.

**НФ:** Фокал видит мир как местный: привычная технология для него незаметна, замечает он сбои и чужое. Импланты и интерфейсы — часть восприятия: что он видит поверх реальности. Объяснения мира законны только глазами новичка или чужака.

## PROMPT:FULL

**Что меняет фильтр:** на чём фокус, что усиливается, что пропадает из поля зрения, как искажается нейтральное.
- страх — слух обострён, зрение сужено, мелкие звуки и движения крупно, красота и уют исчезают, нейтральное читается как угроза, время тянется;
- вина — в нейтральных словах слышится упрёк, кажется, что говорят о нём, всё напоминает об ошибке;
- гнев — всё раздражает, внутренний голос враждебный, досада растёт в возмущение, контекст и объяснения не слышны;
- подавленность — ощущения притуплены, мир без цвета, в каждом действии усталость, будущего времени нет — завтра не представить;
- горе — в речь проникает прошедшее время («раньше», «было»), отсутствие громче присутствия, счёт времени «сколько прошло с тех пор»;
- опьянение — мысли обрывками, провалы во времени, перегрузка или онемение ощущений.

**Приёмы:**
- избирательная деталь — персонаж замечает то, что важно ему: подавленный — мусор и трещины, влюблённый — как человек держит чашку;
- время под фильтром — в страхе тянется, в радости летит, в горе стоит, в скуке ползёт;
- сочетания фильтров сильнее одного: горе и вина, влюблённость и страх отказа.

**Ошибки:**
- фильтр назван прямо: «мне было тоскливо, поэтому всё казалось серым» — покажи серость, не объясняй её;
- фильтр скачет: подавлен в одной главе, беспричинно бодр в следующей — сдвиги постепенные и объяснённые;
- фильтра нет: после потрясения персонаж описывает сцену как протокол.

**Ненадёжный рассказчик** возникает из сильного фильтра: читатель должен иметь возможность заметить искажение раньше, чем его заметит сам персонаж.

---

## 🎯 НАЗНАЧЕНИЕ

Система **фильтров восприятия** — как персонаж искажает реальность через призму своих эмоций, травм, убеждений и состояния.

**"Two people see the same scene. Two completely different stories."**

---

## 🔍 CORE PRINCIPLE

**Reality ≠ POV Character's Perception**

```
OBJECTIVE REALITY:
Man enters room. Says hello. Smiles.

POV FILTER (Paranoid):
He entered—too confident. That smile. 
Fake. Definitely fake. What does he want?

POV FILTER (In Love):
He entered and the room brightened. That smile—
God, that smile. Her heart stumbled.

POV FILTER (Depressed):
Someone entered. She didn't look up. Didn't care.

→ SAME SCENE, 3 DIFFERENT EXPERIENCES
```

---

## 🎭 8 MAJOR EMOTIONAL FILTERS

### 1. FEAR FILTER

**What changes:**
- **Focus:** Threats, dangers, exits
- **Amplifies:** Small sounds, movements
- **Ignores:** Beauty, comfort, positives
- **Time:** Slows (hyperawareness)
- **Sensory:** Hearing amplified, vision tunneled

```
SCENE: Walking home at night

NEUTRAL:
She walked down the street. A cat ran across.

FEAR FILTER:
Every shadow was a threat. Movement—her heart 
stopped. Just a cat. Just a cat. But that noise 
behind? Footsteps? Keep walking. Faster. Where 
was her keys? Couldn't find them. Panic rising—
```

**TECHNIQUES:**
- Short, sharp sentences
- Notice everything suspicious
- Misinterpret neutral things as threats
- Physical reactions (heart rate, breath)
- Paranoid thoughts

---

### 2. GUILT FILTER

**What changes:**
- **Focus:** Own mistakes, judgments
- **Amplifies:** Criticism (real or imagined)
- **Ignores:** Forgiveness, kindness
- **Distorts:** Neutral into accusatory

```
SCENE: Friend says "How are you?"

NEUTRAL:
"How are you?" Anna asked.

GUILT FILTER:
"How are you?" 
The emphasis on ARE. She knows. Of course she knows.
Everyone knows what I did. That look—judgment. 
Or am I imagining it? No. Definitely judgment.
```

**TECHNIQUES:**
- Read criticism into neutral comments
- Assume people are talking about them
- Self-flagellation in narration
- Avoidance of eye contact
- Everything reminds them of mistake

---

### 3. LOVE/INFATUATION FILTER

**What changes:**
- **Focus:** The person (hyperaware)
- **Amplifies:** Positive qualities
- **Ignores:** Red flags, flaws
- **Distorts:** Everything becomes romantic

```
SCENE: Person texting

NEUTRAL:
He looked at his phone.

LOVE FILTER:
He looked at his phone. Texting her? Probably her.
That small smile—definitely her. God, the way his 
fingers moved across the screen. Even that was 
attractive. When did typing become hot?
```

**TECHNIQUES:**
- Notice tiny details (way they hold pen)
- Interpret everything positively
- Physical reactions (butterflies, warmth)
- World feels brighter
- Time stops when they're near

---

### 4. ANGER FILTER

**What changes:**
- **Focus:** Injustices, offenses
- **Amplifies:** Annoyances into outrages
- **Ignores:** Context, explanations
- **Distorts:** Neutral into hostile

```
SCENE: Someone bumps into them

NEUTRAL:
Someone bumped into her in the crowd.

ANGER FILTER:
Someone SHOVED her. Didn't even apologize. 
Typical. Everyone in this city is a selfish 
asshole. She wanted to turn around, say something—
but what's the point? They wouldn't care. Nobody cares.
```

**TECHNIQUES:**
- Everything irritates
- Inner monologue hostile
- Notice only negative
- Escalate internally
- Physical tension

---

### 5. DEPRESSION FILTER

**What changes:**
- **Focus:** Bleakness, emptiness
- **Amplifies:** Negatives
- **Ignores:** Joy, beauty, hope
- **Dulls:** All sensation, color

```
SCENE: Beautiful sunset

NEUTRAL:
The sunset painted the sky orange and pink.

DEPRESSION FILTER:
The sun was setting. Another day ending. 
Another day survived. The sky was... colors. 
She used to care about sunsets. When did she 
stop caring? Doesn't matter. Nothing matters.
```

**TECHNIQUES:**
- Emotional numbness in narration
- Lack of sensory detail (world grayed)
- Fatigue in every action
- No future tense (can't imagine tomorrow)
- Everything effort

---

### 6. PARANOIA FILTER

**What changes:**
- **Focus:** Hidden meanings, conspiracies
- **Amplifies:** Coincidences into patterns
- **Ignores:** Simple explanations
- **Distorts:** Innocent into sinister

```
SCENE: Coworker smiles

NEUTRAL:
Mark smiled at her in the hallway.

PARANOIA FILTER:
Mark smiled. Why? He never smiles at her. 
Unless—did he hear something? About the project? 
Is this a setup? That smile was wrong. Practiced. 
He's in on it. They all are.
```

**TECHNIQUES:**
- Question everything
- See patterns everywhere
- Trust no one
- Everyone has agenda
- Hypervigilance

---

### 7. GRIEF FILTER

**What changes:**
- **Focus:** Reminders of loss
- **Amplifies:** Absence
- **Ignores:** Present moment
- **Distorts:** Everything into reminder

```
SCENE: Coffee shop

NEUTRAL:
The coffee shop was busy.

GRIEF FILTER:
The coffee shop—their coffee shop. She'd sat 
in that corner booth. With him. Every Sunday. 
The barista didn't recognize her without him. 
Of course not. She was invisible now. Half a person.
```

**TECHNIQUES:**
- Everything triggers memory
- Past tense infiltrates (was, used to)
- Absence louder than presence
- Time markers (how long since)
- Physical weight to everything

---

### 8. INTOXICATION FILTER

**What changes:**
- **Focus:** Shifts erratically
- **Amplifies:** Emotions, sensations
- **Ignores:** Consequences, logic
- **Distorts:** Time, distance, clarity

```
SCENE: At bar

NEUTRAL:
The bar was crowded and loud.

DRUNK FILTER:
Loud. So loud. Why's everyone shouting? 
The floor tilted. No—she tilted. Okay. Okay.
Focus. That guy—was he looking at her? Definitely 
looking. Maybe. What was she doing? Right. Leaving. 
Where's the door? There. No, there. Fuck.
```

**TECHNIQUES:**
- Fragmented thoughts
- Sensory overload OR numbness
- Poor judgment in narration
- Time skips
- Physical disorientation

---

## 🎨 ADVANCED FILTER COMBINATIONS

### GRIEF + GUILT

```
Everything reminds her of him (grief) AND her failure 
to save him (guilt). Double filter = devastating.

SCENE: His empty chair

She couldn't look at his chair. Empty. 
Her fault it was empty. If she'd just—
but she didn't. And now. Empty. Forever.
```

---

### LOVE + FEAR

```
Attracted to someone BUT afraid of rejection/intimacy.

SCENE: First date

He's perfect. Too perfect. Which means he'll 
figure out she's not. Any moment now. That pause—
there. He's realizing. She should leave before he does.
```

---

## 🔧 FILTER TECHNIQUES

### TECHNIQUE 1: SELECTIVE DETAIL

**Character notices what matters to THEM:**

```
DEPRESSION FILTER:
Notices: garbage on street, graffiti, broken things
Ignores: flowers, children playing, sunshine

LOVE FILTER:
Notices: their laugh, way they hold coffee, small gestures
Ignores: everyone else in room
```

---

### TECHNIQUE 2: SENSORY BIAS

**Each filter affects senses differently:**

| Filter | Primary Sense | Effect |
|--------|---------------|--------|
| Fear | Hearing | Amplified, every sound = threat |
| Depression | None | All dulled |
| Anger | Physical | Tension, heat |
| Love | Vision | Everything beautiful |
| Grief | Memory | Constant flashbacks |
| Paranoia | Vision | Hypervigilant scanning |

---

### TECHNIQUE 3: TEMPORAL DISTORTION

**Filters change time perception:**

```
FEAR: Time slows (feels like hours)
JOY: Time flies (where did it go?)
GRIEF: Time stops (stuck in past)
BOREDOM: Time crawls
```

---

### TECHNIQUE 4: INTERPRETIVE SHIFT

**Same event, different meaning:**

```
EVENT: Friend cancels plans

NEUTRAL: "Plans changed."

FILTERS:
Depression: "Nobody wants to see me."
Paranoia: "They're avoiding me. Why?"
Guilt: "I did something wrong."
Relief: "Thank god, I didn't want to go anyway."
```

---

## 📊 FILTER INTENSITY SCALE

```
LEVEL 1: SUBTLE (Background)
Filter present but not dominant.
Reader barely notices.

LEVEL 2: PRESENT (Noticeable)
Filter colors perception clearly.
Reader aware of bias.

LEVEL 3: STRONG (Distorting)
Filter significantly warps reality.
Unreliable narrator territory.

LEVEL 4: OVERWHELMING (Consuming)
Filter IS reality for character.
Complete distortion.

LEVEL 5: PSYCHOTIC BREAK
Filter creates hallucinations, delusions.
Character lost in it.
```

---

## ⚠️ WHEN FILTERS GO WRONG

### MISTAKE 1: TOO OBVIOUS

```
❌ BAD:
"I was depressed, so everything looked gray and sad."

✅ GOOD:
The world was... there. Existing. She supposed 
people found it interesting. She didn't remember why.
```

---

### MISTAKE 2: INCONSISTENT

```
❌ BAD:
Character depressed in Ch3, suddenly optimistic in Ch4 
with no transition.

✅ GOOD:
Track filter intensity. Show shifts gradually.
```

---

### MISTAKE 3: NO FILTER

```
❌ BAD:
Character just had traumatic event. Describes scene 
objectively, no emotional filter.

✅ GOOD:
Trauma changes perception. Apply appropriate filter.
```

---

## 📋 FILTER CHECKLIST

**For each scene:**

- [ ] What's character's emotional state?
- [ ] Which filter(s) apply?
- [ ] What does this filter make them notice?
- [ ] What does this filter make them ignore?
- [ ] How does it distort neutral events?
- [ ] Intensity level appropriate?
- [ ] Consistent with previous scenes?
- [ ] Shifts explained/gradual?

---

## 🏆 UNRELIABLE NARRATOR

**Filters create unreliable narration:**

```
STRONG FILTER = UNRELIABLE

Reader must question: Is this real or filtered?

EXAMPLE: Paranoid narrator
Everything they report sounds suspicious.
Reader doesn't know what's real vs paranoid.
Climax reveals truth.

TECHNIQUE:
1. Establish filter early
2. Reader learns to compensate
3. Twist: filter was RIGHT (or WRONG)
```

---

**ВЕРСИЯ:** 1.0  
**РАЗМЕР:** ~10 KB  

**"We don't see the world as it is. We see it as we are."**
