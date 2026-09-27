# 👁️👂👃👅✋ SENSORY IMMERSION ENGINE v1.0

**Модуль:** advanced_engines/22_sensory_immersion.md  
**Версия:** 1.0.0  
**Рейтинг:** 5/5  
**Зависимости:** descriptions.md

---

## PROMPT:QUICK

<!-- Секции PROMPT:QUICK и PROMPT:FULL — ровно то, что движок отдаёт модели.
     QUICK идёт во всех режимах, FULL — дополнение для QUALITY и MASTER.
     Всё ниже них — справочник для автора, в промпт не попадает.
     Без код-блоков: они в промпт не идут. -->

**Пиши не только зрением.** По умолчанию 80–90% деталей — визуальные. Ориентир на сцену: зрение 50–60%, звук 20–25%, осязание 15–20%, запах 10–15%, вкус 2–5%. Минимум три чувства из пяти.

**Запах** — сильнейший триггер памяти и атмосферы: одна точная деталь запаха делает сцену реальной.

**Правило на сцену:** назови доминирующее чувство сцены — и пусть это будет не зрение.

**Конкретно, а не вообще:** не «пахло плохо» и «раздался шум», а что именно пахло и что именно звучало. Не «тишина была оглушительной» — опиши, что конкретно стихло и почему это страшно.

### Жанровые приоритеты сенсорики

**ХОРРОР:** Звук и запах важнее зрения. Звуки, которых быть не должно; холод без причины; скользкое и влажное под рукой. Зрение — последним, когда угроза уже рядом.

**РОМАНТИКА:** Запах человека — его собственный, не парфюм; тепло тела; звук дыхания; расстояние между героями как физическое ощущение. Прикосновение скупо до установившейся химии, потом подробно.

**ДЕТЕКТИВ/НУАР:** Зрение — детали места и улики. Запахи табака, алкоголя, дождя, смерти; город звуковым фоном; горечь во рту; температура как время суток и настроение.

**ТРИЛЛЕР:** Точная физиология стресса вместо общих штампов; обострённый слух и реакция на движение; пот, дрожь, пульс.

**ФЭНТЕЗИ:** Магия — через тело: что именно чувствует персонаж, когда она действует. Чужой мир — через запахи и фактуры раньше, чем через описания; природа мира — через ощущения, а не экспозицию. Каждую магию описывай своими ощущениями, не одной и той же формулой.

**НФ/КИБЕРПАНК:** Синтетические запахи и звуки, человеческое тело в чуждой среде (давление, перегрузка, переработанный воздух), технология через осязание — поверхность, вибрацию, температуру устройств.

**РЕАЛИЗМ:** Бытовая сенсорика: запах кухни, скрип половицы, вес пальто. Детали, которых никто не замечает, и делают сцену настоящей.

## PROMPT:FULL

**Что даёт каждое чувство:**
- звук — атмосфера и напряжение: голоса, дыхание, шаги, механизмы, природа; тишина как отсутствие ожидаемого звука;
- осязание — близость, уязвимость, реальность: фактура, температура, боль, давление, контакт кожи с тканью, металлом, кожей;
- запах — мгновенная эмоция и память: приятный, отталкивающий, нейтральный, запах детства, запах-предупреждение (газ, дым, плесень);
- вкус — редко, но телесно и запоминаемо: буквальный и вкус страха во рту.

**Жанровый баланс:** в хорроре меньше зрения (воображение заполняет пробелы), больше звука; в романтике больше осязания; в триллере зрение и звук держат саспенс; в литературной прозе запаха больше обычного и он слоистее.

**Приёмы погружения:**
- у персонажа есть ведущее чувство: повар входит в комнату носом, музыкант — ухом, и эта оптика характеризует его;
- нарастание: чувства подключаются одно за другим, и сцена становится почти невыносимо телесной;
- лишение: убери одно чувство (темнота), и остальные обостряются — уязвимость, близость или ужас;
- синестезия — одно чувство через другое; редко, иначе становится манерностью.

**Ошибки:**
- только зрение: цвет стен, рост человека — и больше ничего;
- общие слова вместо конкретной детали;
- невозможная сенсорика для фокала: слепой не «видит», персонаж в другой комнате не различает шёпот.

Сенсорная деталь связана с эмоцией персонажа: он замечает то, что соответствует его состоянию.

---

## 🎯 НАЗНАЧЕНИЕ

Система **полного погружения через все 5 чувств**. Большинство авторов пишут только визуально. Это исправляет проблему.

**"Readers live in sensory detail. Don't starve them."**

---

## 📊 THE PROBLEM

**Default balance (WRONG):**
- Vision: 80-90% 😱
- Sound: 5-10%
- Touch: 2-5%
- Smell: 1-2%
- Taste: 0-1%

**Optimal balance:**
- Vision: 50-60%
- Sound: 20-25%
- Touch: 15-20%
- Smell: 10-15%
- Taste: 2-5%

---

## 👁️ VISION (Sight)

**Use:** 50-60% of sensory details

**Techniques:**
- Color, shape, movement
- Light vs dark
- Patterns, textures (visual)
- Facial expressions
- Body language

**Avoid:** ALL vision, zero other senses

---

## 👂 SOUND (Hearing)

**Use:** 20-25% (MORE than you think!)

**Power:** Sound = atmosphere, emotion, tension

```
EXAMPLES:

SILENCE (powerful):
"The house was silent. Not peaceful—wrong. 
The silence of held breath."

SUDDEN SOUND (shock):
"Glass shattered. She froze."

AMBIENT (immersion):
"Traffic hum. Distant sirens. Someone's TV through 
thin walls. The soundtrack of the city."

RHYTHM (music):
"Rain drummed on the roof. Steady. Relentless. 
Like a heartbeat that wouldn't stop."
```

**SOUND CATEGORIES:**
- Human (voices, breathing, footsteps)
- Environmental (wind, rain, traffic)
- Mechanical (engines, phones, doors)
- Natural (birds, water, rustling)
- Silence (absence = powerful)

---

## ✋ TOUCH (Tactile)

**Use:** 15-20% (HIGHLY underused!)

**Power:** Touch = intimacy, vulnerability, reality

```
EXAMPLES:

TEXTURE:
"Rough brick under her fingertips. Real. Solid."

TEMPERATURE:
"Cold metal. Ice against her palm."

PHYSICAL SENSATION:
"Goosebumps. Hair standing. Skin prickling."

CONTACT:
"His hand on her shoulder—warm, steady, grounding."

PAIN:
"Sharp. Burning. Spreading from wrist to elbow."

PRESSURE:
"The weight of the blanket. Comforting. Safe."
```

**TOUCH CATEGORIES:**
- Texture (rough, smooth, soft, hard)
- Temperature (hot, cold, warm, cool)
- Pain (sharp, dull, burning, throbbing)
- Pressure (tight, loose, heavy, light)
- Contact (skin-to-skin, fabric, metal)

---

## 👃 SMELL (Olfactory)

**Use:** 10-15% (MOST powerful memory trigger!)

**Power:** Smell = instant emotion, memory, atmosphere

```
EXAMPLES:

MEMORY TRIGGER:
"Coffee. Dad's coffee. Sunday mornings. Before."

ATMOSPHERE:
"The bar smelled of stale beer and old regret."

CHARACTER:
"She wore vanilla. Always vanilla. He'd know 
her blind in a crowd."

EMOTION:
"Hospital smell—antiseptic trying to hide death. 
Failing."

PLACE:
"The library: old paper, dust, quiet centuries."
```

**SMELL CATEGORIES:**
- Pleasant (flowers, food, perfume)
- Unpleasant (rot, smoke, chemicals)
- Neutral (rain, wood, metal)
- Nostalgic (childhood scents)
- Warning (gas, smoke, mold)

---

## 👅 TASTE (Gustatory)

**Use:** 2-5% (Less frequent, but powerful)

**Power:** Taste = visceral, memorable

```
EXAMPLES:

LITERAL:
"Blood. Copper. She'd bitten her tongue."

FEAR:
"Fear tasted like metal. Like electricity."

MEMORY:
"The cake tasted like childhood—butter, sugar, 
Mom's kitchen."

ATMOSPHERE:
"The air tasted of ash. The city was burning."

DISGUST:
"Bile rose. She swallowed it down."
```

---

## 📊 SENSORY BALANCE TRACKER

```python
def analyze_sensory_balance(scene):
    """
    Counts sensory details by type
    """
    counts = {
        "vision": count_visual_details(scene),
        "sound": count_auditory_details(scene),
        "touch": count_tactile_details(scene),
        "smell": count_olfactory_details(scene),
        "taste": count_gustatory_details(scene)
    }
    
    total = sum(counts.values())
    percentages = {k: (v/total)*100 for k, v in counts.items()}
    
    # Check balance
    issues = []
    if percentages["vision"] > 70:
        issues.append("⚠️ TOO VISUAL (>70%)")
    if percentages["sound"] < 15:
        issues.append("⚠️ ADD MORE SOUND (<15%)")
    if percentages["touch"] < 10:
        issues.append("⚠️ ADD MORE TOUCH (<10%)")
    if percentages["smell"] < 5:
        issues.append("⚠️ ADD MORE SMELL (<5%)")
    
    return {
        "balance": percentages,
        "issues": issues,
        "recommendation": generate_recommendations(percentages)
    }
```

---

## 🎭 GENRE-SPECIFIC RATIOS

### HORROR
```
Vision: 40% (less = scarier, imagination fills gaps)
Sound: 35% (creaks, whispers, silence)
Touch: 15% (cold, crawling sensation)
Smell: 8%  (rot, decay)
Taste: 2%  (fear, blood)

WHY: Sound + darkness = terror
```

### ROMANCE
```
Vision: 45%
Sound: 20% (voice, laughter, breath)
Touch: 25% (CRITICAL for intimacy)
Smell: 8%  (perfume, skin)
Taste: 2%  (kisses, food)

WHY: Touch = connection
```

### THRILLER
```
Vision: 50% (need to see action)
Sound: 30% (gunshots, footsteps, breathing)
Touch: 15%
Smell: 4%
Taste: 1%

WHY: Visual + auditory for suspense
```

### LITERARY
```
Vision: 45%
Sound: 20%
Touch: 15%
Smell: 15% (MORE than usual, layered)
Taste: 5%

WHY: Rich sensory = immersion
```

---

## 🔧 IMMERSION TECHNIQUES

### TECHNIQUE 1: SYNESTHESIA

**Cross senses:**

```
"The silence was thick, almost visible."
(Sound → Vision)

"Her voice was warm velvet."
(Sound → Touch + Temperature)

"The music tasted like summer."
(Sound → Taste + Season)
```

---

### TECHNIQUE 2: CHARACTER SIGNATURE SENSE

**Each character notices different senses:**

```
CHEF (taste/smell primary):
"He entered the kitchen. Garlic, rosemary, 
something burning underneath. Amateur."

MUSICIAN (sound primary):
"The room hummed—AC unit, B-flat. 
Fluorescent lights, higher pitch. Dissonant."

TACTILE PERSON (touch primary):
"Rough carpet. Cheap. The kind that scratches 
bare feet. Table edges sharp."
```

---

### TECHNIQUE 3: SENSORY CRESCENDO

**Layer senses for intensity:**

```
BUILDING:

Vision: The door opened.
+ Sound: Hinges creaked.
+ Touch: Cold air rushed in.
+ Smell: Rot. Death.
+ Taste: She gagged.

EFFECT: Overwhelming, visceral
```

---

### TECHNIQUE 4: SENSORY DEPRIVATION

**Remove sense to heighten others:**

```
DARK ROOM (no vision):
Sound amplified. Every creak. Every breath.
Touch hypersensitive. Air moving. Someone close.
Smell stronger. Sweat. Fear. Cologne.

EFFECT: Vulnerability, intimacy, or terror
```

---

## ⚠️ SENSORY MISTAKES

### MISTAKE 1: ALL VISION

```
❌ "The room was blue with white curtains. 
    The man was tall."

✅ "The room—blue walls, white curtains snapping 
    in the breeze (sound). Sunlight warm on her 
    skin (touch). Smell of fresh paint (smell)."
```

### MISTAKE 2: GENERIC SENSORY

```
❌ "It smelled bad."
❌ "He heard a noise."

✅ "Rot—sweet, organic, wrong."
✅ "Glass breaking. Sharp. Close."
```

### MISTAKE 3: IMPOSSIBLE POV SENSORY

```
❌ Character blind:
   "He saw the red car."

✅ "Tires on gravel. Close. Car door slam. 
    Engine—smooth, expensive."
```

---

## 📋 SENSORY CHECKLIST

**Every scene (1-2 pages):**

- [ ] Multiple senses used? (minimum 3 of 5)
- [ ] Vision under 70%?
- [ ] Sound present?
- [ ] Touch included?
- [ ] Smell when appropriate?
- [ ] Specific details (not "smelled bad")?
- [ ] Character signature sense?
- [ ] Sensory = emotional state?

---

## 🏆 SENSORY MASTERY

**Signs of mastery:**
- Reader can FEEL the scene
- All 5 senses engaged
- Specific, not generic
- Sensory = character + emotion
- Balanced distribution
- Memorable details

---

**ВЕРСИЯ:** 1.0  
**РАЗМЕР:** ~8 KB  
**УРОВЕНЬ:** 5/5 Professional  
**СТАТУС:** ✅ PRODUCTION READY

**"Make them see it, hear it, feel it, smell it, taste it. Make it REAL."**
