# ADAPTIVE TENSION CURVE ENGINE v1.0

**Модуль:** advanced_engines/tension_curve.md  
**Версия:** 1.0.0  
**Зависимости:** CORE_FULL.md, scene_structure.md

---

## 🎯 НАЗНАЧЕНИЕ

Динамическая система управления напряжением в реальном времени. Анализирует кумулятивную усталость читателя и автоматически рекомендует оптимальную интенсивность следующей главы.

---

## 📊 КОМПОНЕНТЫ СИСТЕМЫ

### 1. TENSION TRACKING (Отслеживание напряжения)

**Метрики интенсивности главы:**
```json
{
  "chapter": 5,
  "intensity": 7,
  "type": "action",
  "emotional_load": 8,
  "cognitive_load": 5,
  "duration_feeling": "medium"
}
```

**Типы интенсивности:**
- **1-3:** Отдых (рефлексия, worldbuilding, спокойный диалог)
- **4-6:** Средняя (расследование, социальные сцены, subplot развитие)
- **7-8:** Высокая (конфликт, откровение, эмоциональный пик)
- **9-10:** Критическая (экшен, кульминация, major revelation)

---

### 2. CUMULATIVE FATIGUE MODEL (Модель усталости)

**Правила накопления:**
```
3+ главы интенсивности 7+ подряд = HIGH FATIGUE
→ Следующая глава должна быть 3-5/10

2+ главы интенсивности 1-3 подряд = BOREDOM RISK  
→ Следующая глава должна быть 6-8/10

Оптимальный ритм: HIGH → MEDIUM → HIGH → LOW → HIGH
```

**Формула усталости:**
```
Fatigue Score = (sum(last_3_chapters.intensity) / 3) × emotional_density_coefficient

Если Fatigue > 7.5 → нужен отдых
Если Fatigue < 3.5 → нужен всплеск
```

---

### 3. EMOTIONAL TEMPERATURE GRAPH (График эмоциональной температуры)

**Визуализация книги:**
```
Intensity
10 |                    *         *
 9 |                  *   *     *   
 8 |        *       *       * *     
 7 |      *   *   *           
 6 |    *       *              *   
 5 |  *                          * 
 4 | *                             *
   |________________________________
    1  3  5  7  9  11 13 15 17 19 21  Chapters

Проблема: Главы 7-13 = 6 глав высокой интенсивности подряд
Риск: Reader burnout в акте 2
```

**Оптимальная кривая:**
```
ACT 1: Волна (5 → 7 → 4 → 8 → 6)
ACT 2: Эскалация (5 → 6 → 8 → 5 → 7 → 9 → 4)  
ACT 3: Финальный всплеск (6 → 8 → 10 → 7 → 5)
```

---

### 4. AUTO-RECOMMENDATIONS (Автоматические рекомендации)

**Система советов:**

```json
{
  "chapter_next": 6,
  "analysis": {
    "last_3_chapters": [8, 7, 9],
    "fatigue_score": 8.0,
    "risk": "HIGH - Reader burnout imminent"
  },
  "recommendation": {
    "intensity": "3-4/10",
    "type": "reflection/character development",
    "reason": "После 3 интенсивных глав читателю нужен отдых",
    "suggested_elements": [
      "Спокойный диалог",
      "Внутренний монолог героя",
      "Worldbuilding детали",
      "Subplot романтики (low stakes)"
    ],
    "avoid": [
      "Экшен",
      "Major revelation",
      "Новые конфликты"
    ]
  }
}
```

---

## 🎨 ПРАКТИЧЕСКОЕ ПРИМЕНЕНИЕ

### ПРИМЕР 1: Детектив-нуар

**Ситуация:**
```
Главы 1-4:
Ch1: 6/10 (труп найден)
Ch2: 7/10 (вторая жертва)  
Ch3: 8/10 (погоня)
Ch4: 9/10 (покушение на детектива)

Fatigue = (7+8+9)/3 = 8.0 → HIGH
```

**Рекомендация:**
```
Глава 5: 3-4/10
Тип: Рефлексия + расследование спокойное
Содержание:
- Детектив в баре, думает
- Диалог с информатором (без драки)
- Анализ улик
- Subplot романтики (звонок от femme fatale)

Избегать: погони, экшена, новых трупов
```

---

### ПРИМЕР 2: Эпическое фэнтези

**Ситуация:**
```
Главы 10-13 (Акт 2):
Ch10: 3/10 (путешествие, описания)
Ch11: 4/10 (разговоры у костра)
Ch12: 3/10 (worldbuilding, история)
Ch13: 4/10 (планирование)

Fatigue = (3+4+3)/3 = 3.3 → BOREDOM RISK
```

**Рекомендация:**
```
Глава 14: 7-8/10
Тип: Action / Revelation
Содержание:
- Внезапная атака
- Major revelation о квесте
- Один из героев ранен
- Конфликт внутри группы

Обязательно: динамика, эмоциональный пик
```

---

## 🔧 ТИПЫ ГЛАВ ДЛЯ БАЛАНСА

### LOW INTENSITY (1-4/10)
**Когда использовать:** После серии интенсивных глав

**Типы:**
- **Рефлексия:** Герой думает, осмысляет
- **Worldbuilding:** Описание мира, культуры, магии
- **Character moment:** Личный момент без stakes
- **Subplot развитие:** Романтика, дружба, хобби
- **Планирование:** Герои обсуждают стратегию

**Техники:**
- Длинные предложения
- Описательная проза
- Внутренний монолог
- Спокойные диалоги

---

### MEDIUM INTENSITY (5-6/10)
**Когда использовать:** Основной режим, между пиками

**Типы:**
- **Расследование:** Сбор улик, опросы
- **Социальные сцены:** Переговоры, интриги
- **Путешествие:** Дорога с небольшими препятствиями
- **Subplot прогресс:** Развитие второстепенных линий

**Техники:**
- Баланс диалога и действия
- Средние предложения
- Умеренный темп

---

### HIGH INTENSITY (7-8/10)
**Когда использовать:** Ключевые моменты актов

**Типы:**
- **Конфликт:** Ссора, противостояние
- **Revelation:** Важное открытие
- **Эмоциональный пик:** Признание, предательство
- **Препятствие:** Серьёзная проблема

**Техники:**
- Короткие предложения
- Динамичный темп
- Эмоциональная нагрузка

---

### CRITICAL INTENSITY (9-10/10)
**Когда использовать:** Кульминации актов, финал

**Типы:**
- **Экшен:** Битва, погоня, драка
- **Кульминация:** Главное противостояние
- **Major revelation:** Переворачивает всё
- **Катастрофа:** Всё рушится

**Техники:**
- Очень короткие предложения
- Максимальный темп
- Физические/эмоциональные ощущения

---

## 📈 АНАЛИЗ ПРОВИСАНИЙ

---

## ⚡ SCENE ENERGY FLOW SYSTEM

**НОВОЕ В v3.0:** Детальное отслеживание энергии каждой сцены и перетекания между ними

### Зачем нужна Scene Energy?

**Проблема:** Глава может быть 8/10 по напряжению, но:
- Вход скучный → читатель не вовлечён
- Выход слабый → нет мотивации читать дальше
- Энергия скачет хаотично → дезориентация

**Решение:** Отслеживать не только общую интенсивность, но и **энергию каждой сцены**

### Метрики Scene Energy

```json
{
  "scene_id": "ch07_sc03",
  "scene_energy": {
    "dramatic_force": 7,
    "risk_level": 8,
    "emotional_amplitude": 6,
    "entry_energy": 5,
    "exit_energy": 9,
    "energy_delta": 4,
    "flow_to_next": "question_cliffhanger",
    "flow_type": "accelerating"
  }
}
```

**Параметры:**

**1. DRAMATIC FORCE (1-10)**  
Сила драматического конфликта в сцене
- 1-3: Exposition, спокойное общение
- 4-6: Конфликт интересов, напряжённость
- 7-8: Открытое противостояние, угроза
- 9-10: Катастрофа, кульминация

**2. RISK LEVEL (1-10)**  
Уровень риска для персонажей
- 1-3: Безопасная обстановка
- 4-6: Потенциальная опасность
- 7-8: Реальная угроза
- 9-10: Жизнь/смерть, точка невозврата

**3. EMOTIONAL AMPLITUDE (1-10)**  
Размах эмоций в сцене
- 1-3: Ровное настроение
- 4-6: Заметные эмоции
- 7-8: Сильные чувства
- 9-10: Эмоциональный шторм

**4. ENTRY ENERGY (1-10)**  
Энергия начала сцены
- Как читатель входит в сцену?
- Есть ли hook?
- Продолжает ли предыдущую энергию?

**5. EXIT ENERGY (1-10)**  
Энергия конца сцены
- Как сцена заканчивается?
- Есть ли cliffhanger?
- Хочется ли читать дальше?

**6. ENERGY DELTA**  
Изменение энергии: `exit_energy - entry_energy`
- Положительное: сцена набирает обороты ✅
- Нулевое: ровная сцена (норм для отдыха)
- Отрицательное: сцена гасит энергию ⚠️

**7. FLOW_TO_NEXT**  
Как энергия перетекает в следующую сцену?
- `question_cliffhanger`: Задан вопрос
- `action_continues`: Действие прерывается
- `emotional_peak`: Эмоциональный пик
- `mystery_deepens`: Загадка усиливается
- `resolution_pause`: Разрешение, пауза

### Flow Types (Типы потока)

**ACCELERATING (Ускоряющийся)**
```
Entry: 3 → Exit: 7 (delta: +4)
Сцена разгоняется, энергия растёт
Использовать: Для build-up к кульминации
```

**SUSTAINED (Устойчивый)**
```
Entry: 7 → Exit: 7 (delta: 0)
Высокая энергия держится
Использовать: Экшен-сцены, погони
```

**DECELERATING (Замедляющийся)**
```
Entry: 8 → Exit: 4 (delta: -4)
Энергия падает
Использовать: После кульминации, resolution
```

**WAVE (Волна)**
```
Entry: 5 → Peak: 9 → Exit: 6
Подъём и частичный спад
Использовать: Драматические сцены с развязкой
```

### Диагностика Energy Flow

**ПРОБЛЕМА 1: ENERGY DROP (Потеря энергии)**
```
Ch7 Scene 3: Exit energy = 9 (cliffhanger!)
Ch7 Scene 4: Entry energy = 3 (спокойное начало)

❌ ПОТЕРЯ ЭНЕРГИИ: -6 единиц
   Читатель разочарован: cliffhanger не разрешён

РЕШЕНИЯ:
1. Усилить вход Scene 4 → entry_energy = 7
2. Снизить выход Scene 3 → exit_energy = 5
3. Объяснить: "Три часа спустя..." (temporal transition)
```

**ПРОБЛЕМА 2: ENERGY PLATEAU (Плато)**
```
Ch10: все 4 сцены имеют energy 7-7-7-7

⚠️  МОНОТОННОСТЬ: Нет динамики
   Читатель устаёт от однородности

РЕШЕНИЕ:
Создать волны: 5-8-4-9 (rhythm!)
```

**ПРОБЛЕМА 3: WEAK EXIT (Слабый выход)**
```
Ch12 Scene 5: Exit energy = 3 (chapter end)

❌ НЕТ МОТИВАЦИИ продолжать чтение

РЕШЕНИЕ:
- Добавить question
- Или добавить reveal
- Или добавить cliffhanger
- Exit energy должен быть ≥ 6 для chapter endings
```

### Energy Flow Между Главами

```json
{
  "chapter_transitions": [
    {
      "from_chapter": 7,
      "to_chapter": 8,
      "ch7_exit_energy": 9,
      "ch8_entry_energy": 8,
      "energy_bridge": "action_continues",
      "reader_experience": "smooth_escalation",
      "status": "✅ GOOD"
    },
    {
      "from_chapter": 12,
      "to_chapter": 13,
      "ch12_exit_energy": 9,
      "ch13_entry_energy": 2,
      "energy_bridge": "none",
      "reader_experience": "jarring_disconnect",
      "status": "❌ FIX NEEDED",
      "suggestion": "Add temporal transition OR start Ch13 stronger"
    }
  ]
}
```

### Рекомендации по Flow

**ПРАВИЛО 1: CLIFFHANGER ДОЛЖЕН РАЗРЕШИТЬСЯ**
```
Exit energy 8-10 → Next entry energy должен быть ≥ 6
```

**ПРАВИЛО 2: ПОСЛЕ ПИКА НУЖЕН СПАД**
```
После сцены 10/10 → следующая сцена 3-5/10 (breath)
```

**ПРАВИЛО 3: CHAPTER ENDINGS**
```
Последняя сцена главы:
- Exit energy ≥ 6 (минимум)
- Exit energy ≥ 8 (желательно)
- Exit energy = 10 (для major cliffhangers)
```

**ПРАВИЛО 4: ACT ENDINGS**
```
Конец акта:
- Либо energy = 9-10 (cliffhanger)
- Либо energy = 2-4 (resolution, pауза)
- НЕ ДЕЛАЙ energy = 5-7 (застревание)
```

### Автоматический анализ

```python
python analyze_scene_energy.py manuscript/

OUTPUT:
╔══════════════════════════════════════╗
║   SCENE ENERGY FLOW ANALYSIS        ║
╚══════════════════════════════════════╝

CHAPTER 7:
  Scene 1: [3→5→7]  ✅ Accelerating
  Scene 2: [7→9]    ✅ Sustained high
  Scene 3: [9→9→9]  ⚠️  Plateau (too flat)
  Scene 4: [9→4]    ❌ Energy drop

TRANSITIONS:
  Ch7→Ch8: [9→8]   ✅ Good bridge
  Ch12→Ch13: [9→2] ❌ ENERGY LOSS -7

RECOMMENDATIONS:
1. Ch7 Scene 3: Add variation (peak at 10?)
2. Ch7 Scene 4: Either strengthen entry OR add bridge
3. Ch13: Start with higher energy (≥6)

OVERALL ENERGY HEALTH: 7.5/10 (Good)
```

### Интеграция с Tension Curve

```
Tension Curve = Общая интенсивность главы
Scene Energy = Детальная карта внутри главы

ПРИМЕР:
Chapter 10: Intensity 7/10
  ├─ Scene 1: Energy 4→6 (build-up)
  ├─ Scene 2: Energy 6→8 (escalation)
  ├─ Scene 3: Energy 8→9 (peak)
  └─ Scene 4: Energy 9→7 (partial resolution)

Средняя энергия сцен: (5+7+8.5+8)/4 ≈ 7.1 ✅ соответствует
```

### Практическое применение

**ДО НАПИСАНИЯ ГЛАВЫ:**
```bash
python plan_scene_energy.py --chapter 15 --target-intensity 8

РЕКОМЕНДАЦИЯ:
Ch15 должна быть 8/10 → запланируй 3-4 сцены:
  Scene 1: [5→7]   "Hook + build-up"
  Scene 2: [7→9]   "Conflict escalates"
  Scene 3: [9→8]   "Peak + resolution начало"
  Scene 4: [8→8]   "Cliffhanger exit"
```

**ПОСЛЕ НАПИСАНИЯ СЦЕНЫ:**
```bash
python rate_scene_energy.py ch15_sc02.md

RESULT:
Dramatic force: 8/10 ✅
Risk level: 7/10 ✅
Emotional amplitude: 9/10 ⚠️  (очень высокая)
Entry: 7 ✅
Exit: 9 ✅
Delta: +2 ✅

ALERT: Emotional amplitude 9/10 истощает читателя
SUGGESTION: Снизить до 7/10 ИЛИ сделать следующую сцену отдыхом
```

---

**Автоматическая диагностика:**

```python
def detect_sagging(chapters):
    problems = []
    
    # Проверка 1: Долгое плато
    for i in range(len(chapters) - 4):
        window = chapters[i:i+5]
        if all(4 <= ch.intensity <= 6 for ch in window):
            problems.append({
                "type": "plateau",
                "chapters": f"{i+1}-{i+5}",
                "issue": "5 глав средней интенсивности без пиков",
                "fix": f"Добавить пик в главе {i+3}"
            })
    
    # Проверка 2: Слишком много отдыха
    for i in range(len(chapters) - 2):
        if all(ch.intensity <= 3 for ch in chapters[i:i+3]):
            problems.append({
                "type": "boredom",
                "chapters": f"{i+1}-{i+3}",
                "issue": "3 низких главы подряд = риск скуки",
                "fix": "Ускорить или объединить главы"
            })
    
    # Проверка 3: Burnout
    for i in range(len(chapters) - 3):
        if all(ch.intensity >= 7 for ch in chapters[i:i+4]):
            problems.append({
                "type": "burnout",
                "chapters": f"{i+1}-{i+4}",
                "issue": "4 интенсивных главы подряд = усталость",
                "fix": f"Снизить интенсивность главы {i+3}"
            })
    
    return problems
```

---

## ✅ ЧЕКЛИСТ ПЕРЕД НАПИСАНИЕМ ГЛАВЫ

```
[ ] Проверил интенсивность последних 3 глав
[ ] Посчитал fatigue score
[ ] Определил оптимальную интенсивность следующей
[ ] Выбрал тип главы (рефлексия/экшен/диалог)
[ ] Знаю, что избегать (если после пиков)
[ ] Знаю, что добавить (если после спада)
[ ] График напряжения выглядит волнообразно
```

---

## 💡 ЗОЛОТЫЕ ПРАВИЛА

1. **Волна, не плато:** Интенсивность должна колебаться
2. **Не >3 высоких подряд:** Читатель устанет
3. **Не >2 низких подряд:** Читатель заскучает
4. **Акт 2 = эскалация:** Общий тренд вверх, но с волнами
5. **После кульминации = отдых:** Дать читателю выдохнуть
6. **Subplot'ы = регуляторы:** Используй для снижения напряжения

---

## 🔗 ИНТЕГРАЦИЯ С ДВИЖКОМ

**Команды:**
```
"Анализ tension curve" → График напряжения всей книги
"Рекомендация для главы [N]" → Оптимальная интенсивность
"Проверка провисаний" → Поиск проблемных участков
"Оптимизация пейсинга" → Предложения корректировок
```

**Автоматически при написании:**
После каждой главы движок:
1. Обновляет tension graph
2. Считает fatigue score
3. Даёт рекомендацию для следующей главы

---

## 🔥 ENHANCED: SCENE ENERGY & FLOW TRACKING

**Добавлено в v3.0 ENHANCED**

### Назначение:
Детальное отслеживание энергии сцен и плавности перехода между главами для максимального reader engagement.

---

### SCENE ENERGY MATRIX

**Для каждой сцены:**

```json
{
  "scene_id": "ch07_s02",
  "chapter": 7,
  "scene": 2,
  
  "scene_energy": {
    "dramatic_force": 7,        // Сила драмы 1-10
    "risk_level": 8,            // Уровень риска для персонажей
    "emotional_amplitude": 6,   // Размах эмоций
    
    "entry_energy": 5,          // Энергия входа в сцену
    "exit_energy": 9,           // Энергия выхода (cliffhanger?)
    "energy_delta": 4,          // Изменение энергии (9-5)
    
    "flow_to_next": "question", // Как перетекает в следующую
    "hook_strength": 8          // Сила хука в конце
  },
  
  "pacing_profile": {
    "tempo": "accelerating",     // slow/steady/accelerating/rapid
    "sentence_length": "short",  // short/medium/long/varied
    "paragraph_density": "tight" // sparse/medium/tight/packed
  },
  
  "reader_state_predicted": {
    "tension": 8,               // Напряжение читателя
    "curiosity": 9,             // Желание узнать что дальше
    "emotional_investment": 7,  // Эмоциональная вовлечённость
    "fatigue": 3                // Усталость (1-10, меньше лучше)
  }
}
```

---

### ENERGY FLOW DIAGNOSIS

**Автоматическая проверка потока энергии между сценами:**

```python
def diagnose_energy_flow(scenes):
    problems = []
    
    for i in range(len(scenes) - 1):
        current = scenes[i]
        next_scene = scenes[i+1]
        
        # ПРОБЛЕМА 1: Потеря энергии
        if current.exit_energy >= 8 and next_scene.entry_energy <= 4:
            energy_loss = current.exit_energy - next_scene.entry_energy
            problems.append({
                "type": "ENERGY DROP",
                "location": f"{current.id} → {next_scene.id}",
                "severity": "high" if energy_loss > 5 else "medium",
                "issue": f"Потеря {energy_loss} единиц энергии",
                "impact": "Читатель теряет momentum, может отложить книгу",
                "fix": [
                    f"Усилить вход {next_scene.id} (текущий: {next_scene.entry_energy} → целевой: {current.exit_energy - 2})",
                    f"ИЛИ снизить выход {current.id} (текущий: {current.exit_energy} → целевой: {next_scene.entry_energy + 2})"
                ]
            })
        
        # ПРОБЛЕМА 2: Plateau (плато энергии)
        if abs(current.energy_delta) < 1:
            problems.append({
                "type": "FLAT SCENE",
                "location": current.id,
                "severity": "medium",
                "issue": "Сцена не меняет энергию (плоская)",
                "impact": "Ощущение стагнации",
                "fix": "Добавить revelation ИЛИ конфликт ИЛИ cliffhanger"
            })
        
        # ПРОБЛЕМА 3: Слишком резкий скачок
        if next_scene.entry_energy - current.exit_energy > 4:
            problems.append({
                "type": "JARRING JUMP",
                "location": f"{current.id} → {next_scene.id}",
                "severity": "medium",
                "issue": "Слишком резкий скачок энергии",
                "impact": "Читатель дезориентирован",
                "fix": "Добавить transition scene ИЛИ smoother opening"
            })
    
    return problems
```

---

### FLOW TYPES (типы перехода)

**1. ESCALATION (эскалация):**
```
Scene A: exit_energy 6 → Scene B: entry_energy 7
Эффект: Нарастание напряжения
Когда использовать: Ближе к кульминации акта
```

**2. CLIFFHANGER (обрыв):**
```
Scene A: exit_energy 9 (вопрос!) → Scene B: entry_energy 8 (ответ начинается)
Эффект: Максимальное "must read next"
Когда использовать: Конец главы перед важным событием
```

**3. BREATHER (передышка):**
```
Scene A: exit_energy 8 → Scene B: entry_energy 3
Эффект: Снижение напряжения, отдых
Когда использовать: После интенсивной сцены, нужна рефлексия
```

**4. CONTRAST (контраст):**
```
Scene A: exit_energy 9 (экшен) → Scene B: entry_energy 2 (тихая сцена)
Эффект: Драматический контраст
Когда использовать: Подчеркнуть эмоциональный вес
```

---

### HOOK TAXONOMY (типы хуков)

**Для exit_energy:**

```json
{
  "hook_types": [
    {
      "type": "question",
      "description": "Сцена заканчивается вопросом",
      "example": "Дверь открылась. В проёме стоял... он?",
      "strength": 9,
      "flow_to_next": "Следующая сцена ДОЛЖНА ответить"
    },
    {
      "type": "threat",
      "description": "Появляется угроза",
      "example": "Телефон зазвонил. Номер неизвестен.",
      "strength": 8,
      "flow_to_next": "Escalation ИЛИ resolution"
    },
    {
      "type": "revelation_partial",
      "description": "Часть информации, хочется больше",
      "example": "Он открыл папку. То что он увидел...",
      "strength": 7,
      "flow_to_next": "Продолжение revelation"
    },
    {
      "type": "decision_pending",
      "description": "Персонаж должен выбрать",
      "example": "У него было 10 секунд. Красный или синий провод?",
      "strength": 9,
      "flow_to_next": "Decision + consequences"
    },
    {
      "type": "arrival",
      "description": "Персонаж прибывает в важное место",
      "example": "Они подъехали к особняку. Он выглядел заброшенным.",
      "strength": 6,
      "flow_to_next": "Exploration"
    }
  ]
}
```

---

### VISUAL ENERGY FLOW CHART

```
CH 7:
Scene 1: Energy [3→5]  ████
Scene 2: Energy [5→9]  ████████▲▲▲  (HOOK: question)
                                ↓
CH 8:
Scene 1: Energy [8→6]  ███████▼   (answers question, then reflection)
Scene 2: Energy [6→8]  ██████▲▲   (new tension)
                                ↓
CH 9:
Scene 1: Energy [7→4]  ██████▼▼   (PROBLEM: energy loss!)

ДИАГНОСТИКА:
✓ Ch7→Ch8: Хороший flow (9→8, smooth transition)
⚠ Ch8→Ch9: Потеря энергии (8→7 ok, но потом 4 слишком низко)
FIX: Усилить вход Ch9 Scene1 ИЛИ добавить intermediate scene
```

---

### MOMENTUM TRACKING

**Отслеживание "инерции" чтения:**

```json
{
  "momentum_score": 8.2,
  
  "calculation": {
    "formula": "Σ(exit_energy * hook_strength) / scene_count",
    "components": {
      "avg_exit_energy": 7.1,
      "avg_hook_strength": 7.8,
      "energy_consistency": 0.85
    }
  },
  
  "interpretation": {
    "8.0+": "Excellent momentum, hard to put down",
    "6.0-7.9": "Good momentum, engaging",
    "4.0-5.9": "Moderate momentum, some drag",
    "< 4.0": "Low momentum, pacing issues"
  },
  
  "weak_points": [
    {
      "location": "Ch12-Ch14",
      "momentum_drop": 3.2,
      "reason": "3 scenes with low hooks подряд",
      "fix": "Strengthen at least one hook in this range"
    }
  ]
}
```

---

### PAGE-TURNER INDEX

**Метрика "невозможно оторваться":**

```python
def calculate_page_turner_index(scenes):
    score = 0
    
    for i in range(len(scenes) - 1):
        current = scenes[i]
        next_scene = scenes[i+1]
        
        # Факторы увеличивающие PTI:
        if current.hook_strength >= 8:
            score += 2  # Сильный хук
        
        if current.exit_energy >= 8 and next_scene.entry_energy >= 7:
            score += 3  # Поддерживается высокая энергия
        
        if current.flow_to_next == "question":
            score += 2  # Вопрос требует ответа
        
        # Факторы снижающие PTI:
        if current.exit_energy - next_scene.entry_energy > 4:
            score -= 2  # Потеря энергии
        
        if current.energy_delta == 0:
            score -= 1  # Плоская сцена
    
    max_score = (len(scenes) - 1) * 7
    pti = (score / max_score) * 100
    
    return {
        "pti": pti,
        "grade": "A" if pti > 80 else "B" if pti > 60 else "C" if pti > 40 else "D",
        "assessment": "Unputdownable" if pti > 80 else "Engaging" if pti > 60 else "Readable" if pti > 40 else "Needs work"
    }
```

---

### ИСПОЛЬЗОВАНИЕ В НАПИСАНИИ

**ПЕРЕД СЦЕНОЙ:**

```
ТЫ: "Пишу Ch8 Scene 2 (допрос священника)"

КЛОД проверяет flow:
- Предыдущая сцена: Ch8 S1 exit_energy = 6 (рефлексия закончилась)
- Текущий fatigue: 4/10 (читатель отдохнул)
- Рекомендуемый entry: 6-7 (плавный подъём)

РЕКОМЕНДАЦИЯ:
"Начни сцену с entry_energy 6-7:
- Средний темп (не rush)
- Открой с небольшим напряжением (священник nervous)
- К концу сцены подними до 8-9 (revelation ИЛИ threat)
- Используй hook_type: 'revelation_partial' для cliffhanger"
```

**ВО ВРЕМЯ НАПИСАНИЯ:**

```
DRAFT написан. Анализ:

Entry_energy: 6 ✓
- Открыли спокойно: "Священник Альдрик ждал в исповедальне"

Mid_energy: 7
- Диалог напрягается: подозрения, уклончивые ответы

Exit_energy: 9 ✓✓
- HOOK: "— Культ? — Священник побледнел. — Они уже здесь."
- Hook_type: threat + question
- Hook_strength: 9/10

FLOW CHECK:
Ch8 S1 [exit 6] → Ch8 S2 [entry 6] = Smooth ✓
Ch8 S2 [exit 9] → Ch9 S1 [entry ?] = Планируй высокий вход!
```

---

### ADVANCED: ENERGY SIGNATURE

**Уникальный энергетический паттерн жанра:**

```json
{
  "detective_noir_signature": {
    "typical_pattern": "Slow build → Revelation spike → Investigation steady → Confrontation peak → Resolution drop",
    
    "scene_energy_distribution": {
      "low (1-3)": "15%",
      "medium (4-6)": "45%",
      "high (7-8)": "30%",
      "critical (9-10)": "10%"
    },
    
    "flow_preferences": {
      "cliffhanger_frequency": "Every 3-4 scenes",
      "breather_after_peak": "Always",
      "escalation_style": "Gradual with sudden spikes"
    }
  }
}
```

---

### МЕТРИКИ КАЧЕСТВА

```json
{
  "scene_energy_score": 88,
  
  "breakdown": {
    "energy_consistency": 92,
    "flow_smoothness": 85,
    "hook_strength_avg": 7.8,
    "momentum_score": 8.2,
    "page_turner_index": 84
  },
  
  "strengths": [
    "Отличный momentum (8.2/10)",
    "Сильные hooks (avg 7.8/10)",
    "Smooth transitions (85% гладкие)"
  ],
  
  "issues": [
    {
      "location": "Ch12→Ch13",
      "issue": "Energy drop (9→4)",
      "severity": "high",
      "fix": "Усилить вход Ch13 до 7"
    }
  ]
}
```

---

**РЕЗУЛЬТАТ ENHANCED VERSION:**
- Каждая сцена имеет измеримую энергию
- Переходы между сценами оптимизированы
- Momentum отслеживается автоматически
- Page-turner качество измеряется

**УРОВЕНЬ:** Professional pacing engineering

---

**Конец модуля: Adaptive Tension Curve Engine**

**Связанные модули:**
- scene_structure.md (композиция сцены)
- genre_techniques.md (жанровый пейсинг)
- INDEX.json (автозагрузка для задачи plan_book)

---

## ## MINI (QUICK режим — суть за 10 строк)

**Интенсивность главы 1-10:**
1-3: Отдых (рефлексия, диалог, worldbuilding)
4-6: Средняя (расследование, subplot, социальные сцены)
7-8: Высокая (конфликт, откровение, эмоциональный пик)
9-10: Критическая (экшн, кульминация, major revelation)

**Правило усталости:** 3+ главы подряд 7+ → читатель устаёт. После пика нужна глава 3-5.
**Правило провисания:** 4+ главы подряд ниже 5 → читатель скучает. Нужен сдвиг.

**Формула нарастания:** не линейно вверх — волнами. Пик → спад → новый пик выше предыдущего.
**Финал арки:** предпоследняя глава 9-10, последняя 5-6 (развязка). Не заканчивай на пике.

**Для этой главы:** оцени предыдущую (1-10) → выбери интенсивность текущей → держи весь текст.

### Жанровые варианты интенсивности

**ХОРРОР:** Нарастание медленнее. Глава 1-5 держи на 2-4 (тревога без угрозы). Пик только к финалу арки. Взрыв в начале убивает жанр — страх живёт в ожидании, не в событии.

**РОМАНТИКА:** Два типа кривых. Химия (нарастает волнами 3→6→4→7→5→9). Конфликт (резкий спад от 8 до 2 в чёрном моменте — потом восстановление к 9). Сцены близости = пик 8-9, но только после установленной химии.

**ДЕТЕКТИВ:** Равномерное давление 5-7 с пиками на раскрытиях (8-9). Финал расследования 9-10. Ошибка — держать 3-4 в середине "для атмосферы": читатель выходит из состояния.

**ТРИЛЛЕР:** Никогда ниже 5. Каждая глава заканчивается хуже чем начиналась. Формула не волны — лестница вверх. Спад допустим только на 1-2 главы максимум и только после экшн-пика.

**РЕАЛИЗМ:** Интенсивность эмоциональная, не событийная. Тихая глава может быть 8 если внутренний конфликт нарастает. Внешнее действие не = высокая интенсивность.
