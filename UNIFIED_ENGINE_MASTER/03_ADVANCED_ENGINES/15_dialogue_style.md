# 💬 DIALOGUE STYLE ENGINE v1.0

**Модуль:** advanced_engines/15_dialogue_style.md  
**Версия:** 1.0.0  
**Зависимости:** dialogues.md, subtext_engine.md

---

## PROMPT:QUICK

<!-- Секции PROMPT:QUICK и PROMPT:FULL — ровно то, что движок отдаёт модели.
     QUICK идёт во всех режимах, FULL — дополнение для QUALITY и MASTER.
     Всё ниже них — справочник для автора, в промпт не попадает.
     Без код-блоков: они в промпт не идут. -->

**Диалог — не то, что говорят, а как.** Один смысл в разных голосах — разные люди.

**Стили и где они работают:**
- острый пинг-понг — короткие реплики, подколки; флирт, соперники, умные герои, разрядка;
- минималистичный — мало слов, вес в несказанном, паузы заполняет тело; горе, стоики, после предательства;
- быстрый обмен — без ремарок, перебивы, обрывки; спор, допрос, паника;
- с подтекстом — безопасная тема на поверхности, опасная под ней; светские сцены, запретные темы, власть;
- циничный — факты без эмоций, самоирония;
- формальный — полные фразы, дистанция;
- уязвимый — незаконченные фразы, персонаж ищет слова;
- манипулятивный — вопросы вместо утверждений, лесть, смена темы;
- бытовой — говорят мимо друг друга, каждый занят своим.

Многословный интеллектуальный и поэтичный стиль — черта конкретного персонажа, а не всех.

**Атрибуция:** «сказал» невидимо, всё остальное — редко и с умыслом. Лучшая атрибуция — действие рядом с репликой.

**Нельзя:** персонаж объясняет другому то, что оба знают, — ради читателя. Нельзя и чувство прямым текстом («я на тебя злюсь!»), и одинаковая речь у всех.

**Правило на сцену:** у каждого персонажа своя длина реплик и свои слова, которых он никогда не скажет.

### Жанровые варианты диалога

**НУАР/ДЕТЕКТИВ:** Циничный стиль, короткие фразы без украшений. Информация — через несказанное. Сыщик спрашивает меньше, чем знает. Диалог — поединок: оба стараются не раскрыться.

**ТРИЛЛЕР:** Под давлением времени — обрывки, недоговорённое. Ложь под давлением — слишком много слов и слишком гладко.

**РОМАНТИКА:** Пинг-понг с паузами, остроумие как флирт. Когда игривый тон ломается — начался настоящий разговор. Признание через метафору, а не прямо.

**ХОРРОР:** Нормальный разговор в ненормальной ситуации: говорят о бытовом, когда угроза очевидна, — отрицание через речь. Тот, кого не слушают, говорит правду.

**РЕАЛИЗМ:** Говорят мимо, отвечают не на вопрос, а на то, что услышали. Перебивают, уходят от больной темы. Паузы — через действие, а не многоточие.

**ФЭНТЕЗИ:** Никакой экспозиции в репликах: персонажи не объясняют друг другу то, что оба знают о своём мире. Речь по сословию и народу — без современного сленга и без сплошной высокопарности. Клятва и обещание в разговоре весят, а не звучат формулой.

**НФ:** Никакого «как ты знаешь, наш корабль...»: персонажи не объясняют друг другу своё устройство мира. Жаргон профессии и среды, сокращения, которые не расшифровывают. Речь машины или ИИ — отдельный голос, но не стереотип робота.

## PROMPT:FULL

**Скорость обмена:**
- медленная — реплика, действие, реплика, действие: вдумчиво, тяжело;
- средняя — две реплики, короткое действие, две реплики: естественно;
- быстрая — реплики подряд без ремарок: резко, на одном дыхании.

**Власть в диалоге.** Сильный говорит коротко, перебивает, не объясняется, задаёт вопросы, ведёт тему; его пауза пугает. Слабый объясняется длинно, извиняется, отвечает, следует за темой, обращается по званию; его пауза выдаёт нервы.

**Приёмы:**
- эхо — ключевое слово повторяется с другим смыслом;
- ответ вопросом — уход от прямого ответа;
- отсылка — реплика из прошлой сцены возвращается и бьёт иначе;
- молчание — ответ даёт действие, а не слова;
- оборванный монолог — речь набирает силу, и её перебивают.

**Живая речь неидеальна:** оговорки, начатые и брошенные фразы, повторы. Дозированно: слишком много слов-паразитов утомляет. Нервозность и неловкость хорошо ложатся на такую речь.

**Каждая реплика работает:** раскрывает персонажа, двигает сюжет или создаёт напряжение. Хорошо — всё сразу.

Прямая речь оформляется тире; другое использование тире — только по делу.

---

## 🎯 НАЗНАЧЕНИЕ

Система **стилизации диалогов** — превращение структурно правильных диалогов в стилистически узнаваемые и выразительные.

**"Dialogue isn't about what people say. It's about HOW they say it."**

---

## 🎭 7 DIALOGUE STYLES

### 1. WITTY/BANTER (Остроумный)

**Characteristics:**
- Quick exchanges
- Wordplay
- Comebacks
- Competitive edge
- Playful or aggressive tone

```
EXAMPLE 1 (Playful):
— You're late.
— I'm punctual. You're early.
— By thirty minutes?
— Eager, aren't we?

EXAMPLE 2 (Aggressive):
— Nice tie.
— Nice insult. Did you workshop that?
— Didn't need to. Came naturally.
— Like your bad taste?
```

**RULES:**
- Rhythm: fast, ping-pong
- Sentence length: short (5-10 words avg)
- Subtext: often playful aggression or flirtation
- Avoid: long monologues, explanations

**USE FOR:**
- Romantic tension
- Rival characters
- Smart characters
- Comedy relief
- Establishing chemistry

---

### 2. MINIMALIST (Минималистичный)

**Characteristics:**
- Few words
- Silence between lines
- Weight in what's NOT said
- Every word counts

```
EXAMPLE:
— She left.
— When?
— Tuesday.
— [pause]
— You okay?
— No.

TECHNIQUES:
- One word answers
- Fragments
- Pauses (indicated by action beats)
- Subtext heavy
```

**RULES:**
- Cut everything unnecessary
- Silence = powerful
- Body language fills gaps
- No exposition

**USE FOR:**
- Grief scenes
- Stoic characters
- Tension
- After betrayal
- Awkward situations

---

### 3. RAPID-FIRE (Быстрый обмен)

**Characteristics:**
- No action beats
- Overlapping speech
- Urgent
- Breathless feel

```
EXAMPLE:
— Where is it?
— I don't—
— Don't lie. Where?
— I said I don't—
— You have five seconds.
— Jesus, okay, okay!
— Four.
— The basement! It's in the basement!

TECHNIQUES:
- Interruptions
- Unfinished sentences
- Question → answer → question
- No descriptors (just dialogue)
```

**RULES:**
- Remove ALL action beats
- Short sentences
- Overlaps/interrupts
- High emotion or urgency

**USE FOR:**
- Arguments
- Interrogations
- Action scenes
- Panic
- Reveals under pressure

---

### 4. SUBTEXT-HEAVY (Скрытый конфликт)

**Characteristics:**
- Surface conversation ≠ real conversation
- Double meanings
- Every line layered
- Tension underneath

```
EXAMPLE (talking about "weather", really about relationship):
— Beautiful day.
— Is it? I hadn't noticed.
— You used to notice. Everything.
— People change.
— Some more than others.
— [looks away] Some need to.

TECHNIQUES:
- Metaphors (weather = emotions)
- Evasion
- Deflection
- Pauses loaded with meaning
```

**RULES:**
- Surface topic (safe)
- Real topic (dangerous)
- Reader understands both
- Characters may not

**USE FOR:**
- Passive aggression
- Forbidden topics
- Social settings (can't speak freely)
- Power dynamics
- Romance (can't admit feelings)

---

### 5. VERBOSE/INTELLECTUAL (Многословный)

**Characteristics:**
- Long sentences
- Complex vocabulary
- Ideas over emotion
- Formal

```
EXAMPLE:
— The fundamental issue, if I may elucidate, is not 
whether the decision was correct in a purely utilitarian 
sense, but rather whether it accounted for the inherent 
unpredictability of human nature.
— So you're saying I fucked up.
— In layman's terms, yes.

TECHNIQUES:
- Polysyllabic words
- Subordinate clauses
- Academic tone
- Avoiding emotional words
```

**RULES:**
- Character trait (not all characters)
- Can be condescending or genuine
- Often contrasted with simpler speaker

**USE FOR:**
- Professors, lawyers, intellectuals
- Comedy (contrast)
- Character avoiding emotion
- Formal settings

---

### 6. NATURALISTIC/MESSY (Натуральный)

**Characteristics:**
- Ums, ahs, hesitations
- False starts
- Tangents
- How people actually talk

```
EXAMPLE:
— So I was thinking, you know, about what you said, 
and I—well, not exactly what you said, but more like 
the implication, you know? And I thought, maybe, I mean 
if you're still—are you still interested? Or...?

TECHNIQUES:
- Filler words
- Repetition
- Backtracking
- Run-on sentences
```

**RULES:**
- Use sparingly (too much = annoying)
- Shows nervousness, uncertainty
- Makes character relatable

**USE FOR:**
- Nervous characters
- Lying badly
- Attraction/awkwardness
- Realism beats

---

### 7. LYRICAL/POETIC (Поэтичный)

**Characteristics:**
- Beautiful language
- Metaphors
- Rhythm
- Elevated

```
EXAMPLE:
— The city eats hope. Chews it up and spits out the bones.
— Poetic.
— Accurate.
— You always were a romantic.
— Was. Past tense. The city ate that too.

TECHNIQUES:
- Metaphorical language
- Alliteration
- Imagery
- Music in the words
```

**RULES:**
- Character-specific (not everyone talks this way)
- Can be pretentious if overused
- Works in literary fiction

**USE FOR:**
- Poets, artists, dreamers
- Literary fiction
- Heightened moments
- Character signature

---

## ⚡ EXCHANGE SPEED

### SLOW EXCHANGE (Thoughtful)

```
Rhythm: Line → Beat → Line → Beat

— What do you want from me?

She looked out the window. Rain streaked the glass.

— The truth. For once.

He set down his coffee. It had gone cold.

— You couldn't handle the truth.

EFFECT: Weighted, deliberate, tense
```

---

### MEDIUM EXCHANGE (Conversational)

```
Rhythm: Line → Line → Short beat → Line → Line

— What do you want from me?
— The truth. For once.

He shook his head.

— You couldn't handle the truth.
— Try me.

EFFECT: Natural, balanced
```

---

### FAST EXCHANGE (Urgent)

```
Rhythm: Line → Line → Line → Line (no beats)

— What do you want from me?
— The truth.
— You couldn't handle it.
— Try me.
— Fine. I never loved you.

EFFECT: Rapid, intense, breathless
```

---

## 🎯 POWER DYNAMICS IN DIALOGUE

### HIGH POWER SPEAKER:

**Characteristics:**
- Short answers
- Interrupts
- Doesn't explain
- Asks questions
- Controls topic
- Uses other's name
- Pauses = intimidating

```
EXAMPLE:
— [looks up from phone] Yes?
— I wanted to discuss—
— Not now.
— It's important.
— [stares]
— [stammers] I'll... come back.
```

---

### LOW POWER SPEAKER:

**Characteristics:**
- Long explanations
- Gets interrupted
- Over-apologizes
- Answers questions
- Follows topic
- Uses titles ("sir," "ma'am")
- Pauses = nervous

```
EXAMPLE:
— I'm sorry to bother you, but I was hoping, if you 
have a moment, that maybe we could discuss—
— What?
— The, um, the project. The deadline. I'm worried—
— Fix it.
— Yes. Yes sir. Of course. I'll—
— [leaves]
```

---

## 🛠️ DIALOGUE TECHNIQUES

### TECHNIQUE 1: THE ECHO

**Repeat key word with different meaning:**

```
— I love you.
— Love. [bitter laugh] Love.
```

---

### TECHNIQUE 2: THE NON-ANSWER

**Evade question with question:**

```
— Did you do it?
— Do you really want to know?
— I asked you a question.
— And I asked you one.
```

---

### TECHNIQUE 3: THE CALLBACK

**Reference earlier line:**

```
EARLIER:
— Trust me.
— Famous last words.

LATER:
— [reveals betrayal]
— Famous last words. You were right.
```

---

### TECHNIQUE 4: THE SILENCE

**Let action beat answer:**

```
— Do you love her?

He couldn't look at her.

— [voice breaking] That's my answer then.
```

---

### TECHNIQUE 5: THE MONOLOGUE INTERRUPT

**Build speech, cut it off:**

```
— You want to know why I did it? I'll tell you why. 
Because you never listened. Not once. You'd come home 
and I'd try to tell you about my day and you'd just—
— I'm listening now.
— [pause] Too late.
```

---

## ⚠️ DIALOGUE MISTAKES

### MISTAKE 1: INFO-DUMPING

```
❌ BAD:
— As you know, Bob, we've been partners for ten years 
and you're an expert in forensics who used to work in 
New York before moving here in 2015.

✅ GOOD:
— Ten years, Bob.
— What?
— We've been partners ten years. You owe me coffee.
```

---

### MISTAKE 2: ON-THE-NOSE

```
❌ BAD:
— I'm angry at you!
— Well, I'm angry at you too!

✅ GOOD:
— [slams door]
— Real mature.
— Fuck off.
```

---

### MISTAKE 3: ALL SOUND SAME

```
❌ BAD:
Everyone speaks perfectly, same vocabulary, same rhythm.

✅ GOOD:
Teen: "Whatever."
Professor: "I beg your pardon?"
Cop: "Problem, folks?"
→ Different voices, clear identities
```

---

### MISTAKE 4: TOO PERFECT

```
❌ BAD:
People speak in complete, grammatical sentences.

✅ GOOD:
— Thought you'd—I mean, weren't you supposed to...?
— Yeah, but—
— Never mind.
→ Natural, messy
```

---

## 📊 STYLE DIAGNOSIS

```python
def analyze_dialogue_style(dialogue):
    """
    Identifies dialogue style
    """
    metrics = {
        "avg_line_length": calculate_avg_words(dialogue),
        "interruptions": count_interrupts(dialogue),
        "action_beats": count_beats(dialogue),
        "subtext_indicators": detect_subtext(dialogue),
        "vocabulary_complexity": analyze_vocab(dialogue),
        "exchange_speed": calculate_speed(dialogue)
    }
    
    # Determine style
    if metrics["avg_line_length"] < 7 and metrics["interruptions"] > 3:
        style = "RAPID-FIRE or BANTER"
    elif metrics["avg_line_length"] < 5:
        style = "MINIMALIST"
    elif metrics["vocabulary_complexity"] > 8:
        style = "VERBOSE/INTELLECTUAL"
    elif metrics["subtext_indicators"] > 5:
        style = "SUBTEXT-HEAVY"
    else:
        style = "NATURALISTIC"
    
    return {
        "primary_style": style,
        "effectiveness": rate_effectiveness(style, metrics),
        "suggestions": generate_suggestions(style)
    }
```

---

## ✅ DIALOGUE CHECKLIST

**For each dialogue scene:**

- [ ] Style matches character personality?
- [ ] Power dynamic clear?
- [ ] Exchange speed appropriate?
- [ ] Subtext present (when needed)?
- [ ] Each character sounds different?
- [ ] No info-dumping?
- [ ] Not too "on the nose"?
- [ ] Action beats balance dialogue?
- [ ] Interruptions natural?
- [ ] Reveals character + advances plot?

---

**ВЕРСИЯ:** 1.0  
**РАЗМЕР:** ~10 KB  

**"Great dialogue sounds like eavesdropping on real people. But better."**
