# READER SIMULATION ENGINE v1.0

**Модуль:** advanced_engines/04_reader_simulation.md  
**Версия:** 1.0.0  
**Зависимости:** Вся рукопись, characters, plot_points

---

## 🎯 НАЗНАЧЕНИЕ

ИИ-симуляция восприятия читателя. Предсказывает вопросы, confusion, эмоциональные реакции и satisfaction points.

**Уровень AAA-геймдева для литературы.**

---

## 🧠 МОДЕЛЬ ЧИТАТЕЛЯ

### 1. READER KNOWLEDGE STATE (Состояние знаний)

**Что читатель знает к главе N:**
```json
{
  "chapter": 5,
  "reader_knows": [
    "Иван — изгнанный следователь",
    "Две жертвы с кровавыми печатями",
    "Печати связаны с прошлым Ивана",
    "Мария — бывшая напарница"
  ],
  "reader_suspects": [
    "Иван скрывает что-то важное",
    "Между Иваном и Марией что-то было"
  ],
  "reader_does_not_know": [
    "Кто убийца",
    "Связь с тем пожаром 5 лет назад (детали)",
    "Что Иван скрыл улику в Ch3"
  ]
}
```

---

### 2. READER QUESTIONS (Вопросы читателя)

**Прогноз вопросов после каждой главы:**

**После Ch1:**
```
ОБЯЗАТЕЛЬНО возникнут:
❓ Кто убийца?
❓ Зачем нужны печати?
❓ Что случилось 5 лет назад?

ВОЗМОЖНО возникнут:
❓ Почему Мария позвала именно Ивана?
❓ Что между Иваном и Марией было?
```

**Валидация:**
- ✅ Если ответы даются постепенно = good pacing
- ⚠️ Если вопросы забыты на 5+ глав = hanging thread
- ❌ Если новые вопросы без ответа на старые = confusion overload

---

### 3. CONFUSION POINTS (Моменты непонимания)

**Автоматическая детекция:**

**Пример confusion:**
```
ГЛАВА 7:
Иван: "Я знал, что это случится."

ПРОБЛЕМА: Читатель не знает, ЧТО должно случиться.
Контекст недостаточен.

PREDICTION: 70% читателей запутаются здесь.

РЕШЕНИЕ: Добавить флешбэк или мысль Ивана:
"Я знал, что это случится. Такая же печать была пять лет назад."
```

---

### 4. EMOTIONAL MAP (Эмоциональная карта)

**Прогноз эмоций читателя по главам:**

```
Emotion
10| Joy                      *
 8| Excitement      *           *
 6| Curiosity   * *   *  *
 4| Neutral  *             
 2| Frustration               *
   |________________________________
    1  3  5  7  9  11 13 15 17 19  Ch

ПРОБЛЕМА обнаружена: Ch13 = Frustration
ПРИЧИНА: Герой пассивен 3 главы подряд (Ch11-13)
РЕШЕНИЕ: Добавить proactive действие в Ch12
```

---

### 5. SATISFACTION POINTS (Точки удовлетворения)

**Что приносит satisfaction:**
- ✅ Ответ на долгий вопрос
- ✅ Персонаж растёт/меняется
- ✅ Subplot разрешается
- ✅ Clever twist
- ✅ Эмоциональный payoff

**Отслеживание:**
```json
{
  "promises_made": [
    {"ch": 1, "promise": "Узнаем кто убийца", "status": "pending"},
    {"ch": 3, "promise": "Иван и Мария разрешат конфликт", "status": "paid_off_ch12"}
  ],
  "satisfaction_score_by_chapter": {
    "ch12": 9,  // Иван и Мария воссоединяются (payoff!)
    "ch8": 3,   // Ничего не решилось (low satisfaction)
    "ch15": 10  // Major revelation (высокий payoff)
  }
}
```

---

## 📊 ТИПИЧНЫЕ ПРОБЛЕМЫ И ДЕТЕКЦИЯ

### 1. PASSIVE PROTAGONIST (Пассивный герой)

**Детекция:**
```
Проверка: Герой инициирует действие ИЛИ реагирует?

Ch11: Реагирует (на информацию от других)
Ch12: Реагирует (на нападение)
Ch13: Реагирует (на приказ Марии)

ПРОБЛЕМА: 3 главы подряд = пассивность
PREDICTION: 60% читателей почувствуют фрустрацию

РЕШЕНИЕ: Ch12 → Иван сам принимает решение идти в Старый квартал
```

---

### 2. UNCLEAR MOTIVATION (Непонятная мотивация)

**Детекция:**
```
ГЛАВА 9: Иван внезапно помогает врагу

ПРОБЛЕМА: Читатель не понимает ПОЧЕМУ
Мотивация не установлена.

PREDICTION: 80% читателей запутаются

РЕШЕНИЕ: Ch7 → показать, что Иван чувствует долг перед всеми жертвами
Тогда в Ch9 мотивация ясна.
```

---

### 3. INFO OVERLOAD (Перегруз информацией)

**Детекция:**
```
ГЛАВА 4: Введено 5 новых персонажей + 3 новых локации + 2 subplot'а

PREDICTION: 70% читателей не запомнят всех

РЕШЕНИЕ: Растянуть на 2 главы ИЛИ убрать 2 второстепенных персонажа
```

---

### 4. BROKEN PROMISE (Нарушенное обещание)

**Детекция:**
```
PROMISE (Ch1): "Кровавые печати — ключ к разгадке"
STATUS (Ch24): Печати оказались не важны, убийца просто псих

ПРОБЛЕМА: Broken genre promise (детектив требует логику)
PREDICTION: 90% читателей разочарованы

РЕШЕНИЕ: Печати ДОЛЖНЫ быть важны для раскрытия
```

---

## ✅ READER SIMULATION ЧЕКЛИСТ

**Перед публикацией главы:**

```
[ ] Какие вопросы возникнут у читателя?
[ ] Даны ли ответы на старые вопросы?
[ ] Мотивация персонажа ясна?
[ ] Нет ли confusion points?
[ ] Герой proactive или passive?
[ ] Есть ли satisfaction point в главе?
[ ] Выполнены ли promises, если финал?
```

---

## 💡 ЗОЛОТЫЕ ПРАВИЛА

1. **Знание читателя ≠ знание автора:** Читатель знает только то, что написано
2. **1 вопрос за главу:** Каждая глава отвечает на 1 старый + создаёт 1 новый
3. **Герой proactive 60%+ времени:** Иначе frustration
4. **Promises must pay off:** Каждое обещание жанра = долг
5. **Confusion > 3 абзаца = проблема:** Читатель бросит книгу
6. **Эмоциональная карта волнообразна:** Не плато

---

## 🔗 ИНТЕГРАЦИЯ

**Команды:**
```
"Симуляция читателя главы [N]" → Прогноз реакции
"Вопросы читателя" → Список открытых вопросов
"Проверка promises" → Какие обещания не выполнены
"Confusion analysis" → Где читатель запутается
```

---

## 🔥 ENHANCED: ADAPTIVE READER PERCEPTION 2.0

**Добавлено в v3.0 ENHANCED**

### Назначение:
Динамическая модель восприятия читателя с отслеживанием эмпатии, доверия рассказчику и адаптивными рекомендациями.

---

### EXPANDED READER STATE

**Расширенная модель состояния читателя:**

```json
{
  "reader_state": {
    "tension_level": 7,           // Напряжение читателя (1-10)
    "empathy_level": 8,           // Эмпатия к героям (1-10)
    "comprehension": 9,           // Понимание происходящего (1-10)
    "narrator_trust": 6,          // Доверие рассказчику (1-10)
    "investment": 8,              // Эмоциональная вовлечённость (1-10)
    "fatigue": 4,                 // Усталость от чтения (1-10)
    "satisfaction": 7,            // Удовлетворённость (1-10)
    "frustration": 3              // Фрустрация (1-10)
  },
  
  "genre_expectation_model": {
    "genre": "detective_noir",
    "match_percentage": 85,
    
    "expectations": [
      {"element": "Циничный детектив", "met": true, "strength": 9},
      {"element": "Femme fatale", "met": true, "strength": 6, "note": "Слабовата"},
      {"element": "Моральная амбивалентность", "met": true, "strength": 8},
      {"element": "Twists", "met": true, "strength": 9},
      {"element": "Атмосферный noir mood", "met": true, "strength": 10},
      {"element": "Логическое раскрытие", "met": "pending", "required_by": "chapter 24"}
    ],
    
    "satisfaction_projection": {
      "current": 75,
      "if_all_met": 88,
      "critical_gaps": ["Femme fatale недостаточно опасна/соблазнительна"]
    }
  },
  
  "emotional_journey": {
    "chapter_by_chapter": [
      {"ch": 1, "emotion": "Intrigued (8)", "empathy": 6},
      {"ch": 3, "emotion": "Suspicious (7)", "empathy": 7},
      {"ch": 7, "emotion": "Invested (8)", "empathy": 8},
      {"ch": 12, "emotion": "Shocked (9)", "empathy": 9},
      {"ch": 15, "emotion": "Anxious (8)", "empathy": 8}
    ],
    
    "trajectory": "Positive (engagement growing)",
    "risk_points": ["Ch18: Potential confusion if не объяснить магию"]
  }
}
```

---

### EMPATHY TRACKING

**Отслеживание эмпатии к персонажам:**

```json
{
  "empathy_map": {
    "detective_kael": {
      "current_level": 8,
      "trajectory": "rising",
      
      "empathy_drivers": [
        {
          "moment": "Ch1: Каэль видит фото мёртвого ребёнка",
          "impact": "+2 empathy",
          "reason": "Уязвимость показана"
        },
        {
          "moment": "Ch5: Каэль грубит официантке",
          "impact": "-1 empathy",
          "reason": "Unlikeable behavior"
        },
        {
          "moment": "Ch7: Флешбэк с сестрой",
          "impact": "+3 empathy",
          "reason": "Понимание боли персонажа"
        }
      ],
      
      "empathy_threshold": {
        "critical_minimum": 6,
        "current": 8,
        "status": "healthy",
        "warning": "Если упадёт < 6 → читатель перестанет care"
      }
    },
    
    "maria_voloshina": {
      "current_level": 7,
      "problem": "Empathy plateau (не растёт с Ch5)",
      "recommendation": "Добавить vulnerable момент в Ch10-11"
    }
  },
  
  "empathy_diagnostics": [
    {
      "issue": "Мария empathy статична",
      "severity": "medium",
      "impact": "Читатель меньше переживает за неё",
      "fix": "Показать её страх ИЛИ личную жертву ИЛИ момент слабости"
    }
  ]
}
```

---

### NARRATOR TRUST DYNAMICS

**Доверие к рассказчику (критично для твистов):**

```json
{
  "narrator_trust": {
    "current_level": 6,
    "optimal_for_genre": "5-7 (некоторое недоверие = хорошо для noir)",
    
    "trust_events": [
      {
        "chapter": 2,
        "event": "Рассказчик скрывает информацию от читателя",
        "impact": "-2 trust",
        "justified": true,
        "reason": "Детективный жанр позволяет withholding"
      },
      {
        "chapter": 8,
        "event": "Рассказчик показал flashback который противоречит Ch3",
        "impact": "-3 trust",
        "justified": false,
        "reason": "Continuity error → читатель чувствует обман",
        "severity": "high",
        "fix_needed": "Исправить противоречие"
      }
    ],
    
    "trust_rules": {
      "can_withhold_info": true,
      "reason": "Detective genre convention",
      "limit": "Нельзя лгать читателю (withhold ≠ lie)"
    },
    
    "warning": {
      "if_trust_falls_below": 4,
      "consequence": "Читатель перестанет верить ЛЮБЫМ revelations",
      "current_risk": "medium (trust = 6)"
    }
  }
}
```

---

### ADAPTIVE RECOMMENDATIONS

**Динамические рекомендации на основе reader state:**

```python
def generate_adaptive_recommendations(reader_state):
    recs = []
    
    # Рекомендация 1: Низкая эмпатия
    if reader_state.empathy_level < 6:
        recs.append({
            "trigger": "Empathy < 6",
            "recommendation": "URGENT: Добавить vulnerable момент героя",
            "examples": [
                "Покажи его страх",
                "Момент слабости",
                "Воспоминание о потере",
                "Жест доброты к кому-то слабому"
            ],
            "why": "Если empathy падает → читатель перестаёт care → не дочитает"
        })
    
    # Рекомендация 2: Низкое понимание
    if reader_state.comprehension < 7:
        recs.append({
            "trigger": "Comprehension < 7",
            "recommendation": "Добавить clarity (читатель confused)",
            "techniques": [
                "Диалог-объяснение (естественный)",
                "Internal monologue героя резюмирует",
                "Visual recap (герой перечитывает заметки)"
            ],
            "warning": "НЕ info-dump! Органично вплети"
        })
    
    # Рекомендация 3: Усталость
    if reader_state.fatigue > 6:
        recs.append({
            "trigger": "Fatigue > 6",
            "recommendation": "BREATHER NEEDED (читатель устал)",
            "next_scene_should_be": [
                "Низкая интенсивность (3-4/10)",
                "Спокойный диалог",
                "Рефлексия",
                "Humour (если уместно)"
            ],
            "why": "Fatigue > 6 → attention span падает → skimming начинается"
        })
    
    # НОВОЕ v3.0: Рекомендация 4: Доверие к рассказчику
    if reader_state.narrator_trust < 5:
        recs.append({
            "trigger": "Narrator trust < 5",
            "recommendation": "CRITICAL: Восстановить доверие к нарратору",
            "causes": [
                "Unreliable narrator зашёл слишком далеко",
                "Слишком много contradictions",
                "Логические дыры не объяснены",
                "Deus ex machina использован"
            ],
            "fixes": [
                "Объясни кажущиеся противоречия",
                "Покажи что narrator честен (meta-moment)",
                "Убери convenient solutions",
                "Foreshadowing для будущих reveals"
            ],
            "why": "Narrator trust < 5 → читатель не верит истории → эмоции блокируются"
        })
    
    # НОВОЕ v3.0: Рекомендация 5: Соответствие жанру
    if reader_state.genre_expectation_match < 70:
        recs.append({
            "trigger": "Genre match < 70%",
            "recommendation": "WARNING: Нарушение жанровых обещаний",
            "analysis": reader_state.genre_analysis,
            "examples": {
                "detective": "Где логическое раскрытие? Читатель ждёт clues!",
                "romance": "Химия между героями слабая → romance не ощущается",
                "horror": "Недостаточно atmosphere → не страшно",
                "thriller": "Pace слишком медленный → не thrilling"
            },
            "fixes": "Усиль жанровые элементы ИЛИ переопредели жанр",
            "why": "Genre mismatch → disappointed readers → bad reviews"
        })
    
    # НОВОЕ v3.0: Рекомендация 6: Investment level
    if reader_state.investment < 6:
        recs.append({
            "trigger": "Investment < 6",
            "recommendation": "RAISE STAKES: Читатель не достаточно вовлечён",
            "techniques": [
                "Увеличь personal stakes для героя",
                "Добавь ticking clock",
                "Ухудши ситуацию (complications)",
                "Покажи что герой может ПРОИГРАТЬ",
                "Emotional attachment: покажи что герой потеряет"
            ],
            "measurement": "Investment = empathy × (stakes ÷ 2) × pacing_match",
            "why": "Low investment → читает по диагонали → не дочитает"
        })
    
    return recs
```

---

## 🎯 ADAPTIVE PERCEPTION 2.0 (НОВОЕ)

**Расширенная модель читательского восприятия**

### Reader State — Полная карта

```json
{
  "chapter": 15,
  "reader_state": {
    "tension_level": 7,
    "empathy_level": 8,
    "comprehension": 9,
    "narrator_trust": 6,
    "genre_expectation_match": 85,
    "investment": 8,
    "fatigue": 4,
    "boredom_risk": 2,
    "confusion_level": 1,
    "satisfaction_projection": 82
  },
  
  "genre_analysis": {
    "declared_genre": "detective_noir",
    "genre_elements_delivered": {
      "cynical_detective": true,
      "moral_ambiguity": true,
      "urban_setting": true,
      "femme_fatale": "weak",
      "twists": true,
      "logical_deduction": "pending"
    },
    "reader_expectations": [
      "Expect: Логическое раскрытие mystery ⏳ pending",
      "Expect: Femme fatale arc ⚠️ underdeveloped",
      "Expect: Noir atmosphere ✓ delivered",
      "Expect: Morally gray protagonist ✓ delivered"
    ],
    "satisfaction_if_continues": 75,
    "critical_missing": "Femme fatale needs more development"
  },
  
  "investment_breakdown": {
    "empathy_contribution": 8,
    "stakes_contribution": 7,
    "pacing_contribution": 8,
    "curiosity_contribution": 9,
    "total_investment": 8.0,
    "bottleneck": null
  },
  
  "trust_factors": {
    "logical_consistency": 8,
    "foreshadowing_quality": 7,
    "plot_holes_count": 0,
    "deus_ex_machina_count": 0,
    "promises_kept": 4,
    "promises_broken": 0,
    "trust_score": 6.5,
    "issues": ["Один момент в Ch12 выглядел convenient"]
  },
  
  "emotional_journey": {
    "dominant_emotion": "suspense",
    "secondary_emotions": ["curiosity", "empathy"],
    "emotional_variety": 0.75,
    "emotional_fatigue": 0.3,
    "needs": "Момент tenderness или humour для variety"
  }
}
```

### Динамические правила адаптации

**ПРАВИЛО 1: Empathy Recovery**
```
IF empathy < 6 FOR 2+ chapters:
  INJECT vulnerable moment IN next 1-2 chapters
  OR protagonist does selfless act
  OR show protagonist's internal pain
```

**ПРАВИЛО 2: Comprehension Maintenance**
```
IF comprehension < 7:
  ADD clarity mechanism:
    - Dialogue recap (natural)
    - Visual aid (map, diagram in-story)
    - POV character thinks through facts
  
IF comprehension < 5 (critical):
  URGENT: Info is too dense OR too vague
  SOLUTION: Simplify OR add explicit explanation
```

**ПРАВИЛО 3: Genre Expectation Management**
```
IF genre_match < 70% BY midpoint:
  WARNING: Readers feeling misled
  
OPTIONS:
  A) Strengthen genre elements (preferred)
  B) Reposition genre (risky, needs market test)
  C) Genre blend (explain in blurb)
```

**ПРАВИЛО 4: Investment Maintenance**
```
IF investment < 6:
  CAUSE ANALYSIS:
    - empathy low? → add vulnerable moment
    - stakes low? → raise complications
    - pacing slow? → increase tempo
    - curiosity low? → add mystery/question
  
TARGET: Keep investment ≥ 7 for commercial fiction
```

**ПРАВИЛО 5: Trust Preservation**
```
IF narrator_trust < 6:
  IMMEDIATE ACTION:
    - Explain apparent contradictions
    - Show foreshadowing worked
    - Avoid convenient solutions
  
IF narrator_trust < 4 (critical):
  DANGER: Readers will DNF (Did Not Finish)
  FIX: Major revision needed OR reframe as unreliable narrator story
```

### Adaptive Difficulty Scaling

**Концепция:** Как в играх, история адаптируется к "навыку" читателя

```json
{
  "reader_profile": {
    "genre_familiarity": 0.8,
    "attention_span": 0.7,
    "tolerance_for_complexity": 0.9,
    "preference_for_subtlety": 0.6
  },
  
  "adaptive_settings": {
    "if_genre_familiarity_high": {
      "can_use": "Genre subversion, meta-commentary",
      "can_skip": "Basic trope explanations"
    },
    "if_attention_span_low": {
      "recommend": "Shorter chapters, more cliffhangers",
      "avoid": "Long descriptive passages, complex subplots"
    },
    "if_complexity_tolerance_high": {
      "can_add": "Multiple POVs, non-linear timeline, ambiguity",
      "recommend": "Layered themes, unreliable narrator"
    },
    "if_subtlety_preference_high": {
      "recommend": "Show don't tell, implicit themes",
      "avoid": "On-the-nose dialogue, explicit morals"
    }
  }
}
```

### Real-time Adjustment Triggers

```
КАЖДЫЕ 3 ГЛАВЫ: Пересчитать reader_state
  ↓
ЕСЛИ метрика < threshold:
  → Генерировать recommendations
  → Приоритизировать по severity
  ↓
ПРИМЕНИТЬ в следующих 1-2 главах:
  → Micro-adjustments (scenes)
  → Macro-adjustments (plot)
```

### Примеры адаптивных изменений

**СЦЕНАРИЙ 1: Empathy падает**
```
Ch10: empathy = 5.5 (было 8.0)

АНАЛИЗ:
- Герой совершил questionable act (Ch9)
- Недостаточно internal justification
- Читатель отдалился

ADAPTIVE FIX (Ch11):
+ Добавить сцену: Герой помогает бездомному ребёнку
+ Flashback: Показать почему герой так поступил в Ch9
+ Internal monologue: Герой сам сомневается в своём выборе

РЕЗУЛЬТАТ: empathy восстанавливается до 7.5
```

**СЦЕНАРИЙ 2: Genre mismatch обнаружен**
```
Ch15/24: genre_match = 68% (критично!)

АНАЛИЗ:
Declared: "Romance"
Delivered: 
  ✓ Chemistry: есть
  ⚠️ Романтические моменты: мало (2 сцены из 15 глав)
  ❌ Emotional arc: слабая

ADAPTIVE FIX:
+ Ch16-18: Добавить 3 romantic beats
+ Усилить internal thoughts о любовном интересе
+ Subplot: Romantic conflict (jealousy/misunderstanding)

PROJECTION: genre_match → 82% к Ch20
```

**СЦЕНАРИЙ 3: Narrator trust обрушился**
```
Ch18: narrator_trust = 4.2 (было 7.5)

ПРИЧИНА:
Ch17: Герой внезапно знает информацию без setup
Читатели думают: "Deus ex machina!"

ADAPTIVE FIX (REVISION):
Вернуться в Ch14:
+ Добавить сцену: Герой подслушивает разговор
+ Или: Находит документ с нужной информацией
+ Foreshadowing: Намекнуть что герой что-то знает

РЕЗУЛЬТАТ: narrator_trust восстанавливается до 7.0
```

---

## 📊 SATISFACTION PROJECTION MODEL

**Предсказание финальной удовлетворённости читателя**

```python
def project_satisfaction(reader_state, chapters_remaining):
    base_satisfaction = (
        reader_state.empathy * 0.25 +
        reader_state.investment * 0.20 +
        reader_state.genre_match * 0.20 +
        reader_state.narrator_trust * 0.15 +
        (10 - reader_state.confusion) * 0.10 +
        (10 - reader_state.fatigue) * 0.10
    )
    
    # Проекция трендов
    empathy_trend = calculate_trend(reader_state.empathy_history)
    investment_trend = calculate_trend(reader_state.investment_history)
    
    projected_satisfaction = (
        base_satisfaction +
        empathy_trend * chapters_remaining * 0.1 +
        investment_trend * chapters_remaining * 0.1
    )
    
    return {
        "current_satisfaction": base_satisfaction,
        "projected_final": projected_satisfaction,
        "confidence": 0.75,
        "risks": identify_risks(reader_state),
        "opportunities": identify_opportunities(reader_state)
    }
```

**ПРИМЕР ВЫВОДА:**
```json
{
  "chapter": 18,
  "chapters_remaining": 6,
  "current_satisfaction": 78,
  "projected_final_satisfaction": 82,
  "confidence": 0.75,
  
  "risks": [
    {
      "risk": "Empathy trending down (-0.3/chapter)",
      "impact": "Could reduce final satisfaction by 5-8%",
      "mitigation": "Add vulnerable moment or redemption beat"
    }
  ],
  
  "opportunities": [
    {
      "opportunity": "Genre match trending up (+2%/chapter)",
      "potential": "Could boost final satisfaction by 3-5%",
      "recommendation": "Continue strengthening genre elements"
    },
    {
      "opportunity": "Investment very high (8.5/10)",
      "potential": "Strong ending will have huge payoff",
      "recommendation": "CRITICAL: Don't disappoint with weak climax"
    }
  ]
}
```

---
            "avoid": ["Экшен", "Новые сложные концепции", "Много персонажей"]
        })
    
    # Рекомендация 4: Жанровое соответствие
    if reader_state.genre_match < 70:
        recs.append({
            "trigger": "Genre match < 70%",
            "recommendation": "ЖАНРОВЫЕ ОЖИДАНИЯ НЕ ОПРАВДЫВАЮТСЯ",
            "severity": "critical",
            "analyze": "Какие элементы жанра отсутствуют?",
            "fix": "Усилить жанровые маркеры"
        })
    
    return recs
```

---

### REAL-TIME ADAPTATION

**Пример адаптации в процессе написания:**

```
ГЛАВА 15: Каэль конфронтует Марию

READER STATE перед главой:
- Empathy к Каэлю: 8/10 ✓
- Empathy к Марии: 6/10 ⚠️
- Tension: 7/10 ✓
- Fatigue: 5/10 ✓

АДАПТИВНАЯ РЕКОМЕНДАЦИЯ:
"Empathy к Марии низковата. В конфронтации покажи её POV:
- Почему она сделала что сделала (мотивация)
- Её внутренний конфликт (не просто villain)
- Момент vulnerability (слеза? дрожащий голос?)

ЦЕЛЬ: Поднять empathy к Марии до 7-8 перед финалом,
иначе её жертва в Ch24 не будет emotionally resonate."

СЦЕНА НАПИСАНА → Проверка:
✓ Показан POV Марии
✓ Мотивация ясна
✓ Vulnerability есть (слеза когда она говорит о дочери)

PROJECTED IMPACT:
Empathy Мария: 6 → 8 ✓✓
```

---

### SATISFACTION PROJECTION MODEL

**Прогноз финального удовлетворения читателя:**

```json
{
  "satisfaction_projection": {
    "current_trajectory": 78,
    "projected_final": 82,
    "target": 85,
    "gap": 3,
    
    "contributing_factors": {
      "plot_resolution": {
        "current": 80,
        "weight": 0.4,
        "notes": "Детективная линия логична"
      },
      "emotional_payoff": {
        "current": 85,
        "weight": 0.3,
        "notes": "Отношения Каэль-Мария хорошо развиты"
      },
      "genre_promises": {
        "current": 75,
        "weight": 0.2,
        "notes": "Femme fatale слабовата, снижает noir feel",
        "fix": "Усилить опасность/соблазн Марии в Ch16-18"
      },
      "thematic_depth": {
        "current": 78,
        "weight": 0.1,
        "notes": "Тема искупления работает"
      }
    },
    
    "optimization_path": [
      {
        "action": "Усилить femme fatale аспект Марии",
        "chapters": "16-18",
        "projected_gain": "+3 satisfaction"
      },
      {
        "action": "Добавить один дополнительный twist",
        "chapters": "20",
        "projected_gain": "+2 satisfaction"
      }
    ],
    
    "if_optimized": "82 + 3 + 2 = 87% satisfaction (EXCELLENT)"
  }
}
```

---

### CONFUSION HEAT MAP

**Визуальная карта где читатель confused:**

```
CHAPTERS:     1    5    10   15   20   24
              │    │    │    │    │    │
COMPREHENSION:█████ ████ ███  █████████ ████
CONFUSION:    │    │    ▲    │    │    │
              │    │   High! │    │    │
              
ANALYSIS:
Ch10: Comprehension падает до 3/10 (CRITICAL)
Причина: Магическая система введена без объяснения
Читатель думает: "WTF is happening?"

FIX REQUIRED:
- Добавить exposition в Ch9 (setup)
- ИЛИ диалог-объяснение в Ch10
- ИЛИ показать магию раньше (Ch5-6)

ПОСЛЕ FIX:
Comprehension Ch10: 3 → 7 ✓
```

---

### INVESTMENT CURVE

**Эмоциональная инвестиция во времени:**

```
INVESTMENT LEVEL:
10│                                    ╱╲
 9│                              ╱╲   ╱  ╲
 8│                         ╱╲  ╱  ╲╱    ╲
 7│                    ╱╲  ╱  ╲╱          ╲
 6│               ╱╲  ╱  ╲╱                ╲
 5│          ╱╲  ╱  ╲╱
 4│     ╱╲  ╱  ╲╱
 3│╱╲  ╱  ╲╱
 2│  ╲╱
 1│
  └─────────────────────────────────────────→
   1  5  10  15  20  25  30  35  40  45  CHAPTERS

ANALYSIS:
✓ Рост investment в Акте 1 (1→6)
✓ Поддерживается в Акте 2 (6→8 с волнами)
⚠ Падение в Ch35-37 (нужна boost)
✓ Пик перед финалом (Ch42-45)

RECOMMENDATION:
Добавить emotional beat в Ch36 для поддержания investment
```

---

### ADVANCED: READER PERSONA SIMULATION

**Симуляция разных типов читателей:**

```json
{
  "reader_personas": [
    {
      "persona": "Genre Purist",
      "priorities": ["Genre authenticity", "Tropes done right"],
      "tolerance": {
        "confusion": "low",
        "slow_pacing": "medium",
        "genre_deviation": "very_low"
      },
      "satisfaction_projection": 88,
      "notes": "Любит noir feel, оценит атмосферу"
    },
    {
      "persona": "Character-Driven Reader",
      "priorities": ["Deep characters", "Emotional arcs"],
      "tolerance": {
        "plot_holes": "medium",
        "slow_pacing": "high",
        "weak_plot": "medium"
      },
      "satisfaction_projection": 85,
      "notes": "Оценит психологию Каэля, но хочет больше Марии"
    },
    {
      "persona": "Plot-Focused Reader",
      "priorities": ["Twists", "Logic", "Pacing"],
      "tolerance": {
        "character_depth": "low",
        "slow_introspection": "very_low"
      },
      "satisfaction_projection": 79,
      "risk": "Может найти Ch7-8 слишком медленными"
    }
  ],
  
  "weighted_average": 84,
  "target_audience": "Character-Driven + Genre Purist (80% readership)"
}
```

---

### МЕТРИКИ КАЧЕСТВА

```json
{
  "adaptive_reader_score": 86,
  
  "breakdown": {
    "empathy_management": 88,
    "comprehension_clarity": 82,
    "narrator_trust": 84,
    "genre_match": 85,
    "emotional_journey": 89,
    "satisfaction_projection": 84
  },
  
  "strengths": [
    "Высокая эмпатия к героям",
    "Эмоциональная арка сильная",
    "Жанровые ожидания оправдываются"
  ],
  
  "improvements_needed": [
    {
      "area": "Comprehension в Ch10",
      "current": 3,
      "target": 7,
      "fix": "Добавить exposition магии"
    },
    {
      "area": "Femme fatale strength",
      "current": 6,
      "target": 8,
      "fix": "Усилить опасность/соблазн Марии"
    }
  ]
}
```

---

**РЕЗУЛЬТАТ ENHANCED VERSION:**
- Эмпатия отслеживается динамически
- Адаптивные рекомендации в реальном времени
- Прогноз удовлетворённости читателя
- Мульти-персона симуляция

**УРОВЕНЬ:** Professional reader psychology

---

**Конец модуля: Reader Simulation Engine**

---

## ## MINI (QUICK режим — суть за 10 строк)

**Симуляция читателя = думать за человека который не знает что будет дальше.**

**Три главных читательских вопроса в каждой сцене:**
1. Что происходит? (ориентация — должна быть в первом абзаце)
2. Почему мне важно? (ставки — должны быть ясны к середине)
3. Что будет дальше? (натяжение — должно быть в последнем абзаце)

**Красные флаги пассивности (60% читателей уйдут):**
Герой 3 сцены подряд только реагирует — дай ему принять решение.
Мотивация действия не понятна читателю — объясни через действие, не монолог.
Сцена заканчивается нейтрально — читатель не знает зачем её читал.

**Красный флаг confusion:**
Имена / локации / timeline — если читатель должен вернуться назад чтобы вспомнить, сцена теряет темп.

**Правило на главу:** перечитай первый абзац — читатель знает кто, где, что происходит? Перечитай последний — есть натяжение вперёд?
