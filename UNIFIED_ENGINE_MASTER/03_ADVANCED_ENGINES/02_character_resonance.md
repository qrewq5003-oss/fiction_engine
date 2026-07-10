# CROSS-CHARACTER RESONANCE SYSTEM v1.0

**Модуль:** advanced_engines/02_character_resonance.md  
**Версия:** 1.0.0  
**Зависимости:** characters.json, relationships.json, timeline.yaml

---

## 🎯 НАЗНАЧЕНИЕ

Сеть взаимного влияния персонажей через события. Отслеживает цепные реакции: как действие персонажа А в главе 3 меняет решение персонажа Б в главе 7, что влияет на судьбу персонажа В в главе 12.

**Превращает плоские relationships в живую экосистему.**

---

## 📊 СТРУКТУРА СИСТЕМЫ

### 1. RESONANCE EVENT (Событие резонанса)

**Базовая единица:**
```json
{
  "event_id": "e_ch03_ivan_betrayal",
  "chapter": 3,
  "initiator": "ivan_kryukov",
  "action": "Иван предаёт доверие Марии, скрывая улику",
  "immediate_impact": {
    "maria_voloshina": {
      "emotional": "Чувствует подозрение",
      "trust_delta": -2,
      "decision_change": "Начинает следить за Иваном"
    }
  },
  "ripple_effects": [
    {"character": "maria_voloshina", "chapter": 7, "result": "Отказывает в помощи"},
    {"character": "sergey_korol", "chapter": 12, "result": "Использует раскол"}
  ]
}
```

---

### 2. EMOTIONAL RIPPLE CHAIN (Цепь волн)

**Пример:**
```
Ch3: Иван скрывает улику
  ↓
Ch5: Мария проверяет Ивана (подозрение +3, доверие -2)
  ↓
Ch7: Мария отказывает в помощи (доверие -3)
  ↓
Ch9: Иван в ловушке → Мария спасает (вина +5, доверие +4)
  ↓
Ch12: Совместное спасение (доверие +6, романтика начинается)
```

**Ключ:** Одно действие → 5 волн через 9 глав

---

### 3. TRUST DYNAMICS (Динамика доверия)

**Шкала:**
```
+10: Абсолютное доверие
+7-9: Высокое
+4-6: Среднее
+1-3: Низкое
0: Нейтрально
-1 до -10: Недоверие/враждебность
```

**График:**
```
Trust
+10|              *
 +5|            *
  0|  *     *
 -2|    *
    |_____________
     1  5  9  12  Ch
```

---

### 4. DECISION CASCADE (Каскад решений)

```
Ch3: Иван скрывает улику
  ↓
Ch5: Мария проверяет (из-за подозрений Ch3)
  ↓
Ch7: Иван один (Мария отказала из-за Ch5)
  ↓
Ch9: Мария спасает (вина из-за Ch7)
  ↓
Ch12: Признание (благодарность из-за Ch9)
```

---

## 🎨 ПРАКТИЧЕСКИЕ ПРИМЕРЫ

### ПРИМЕР: Детектив-нуар

**Событие:** Иван скрывает улику (Ch3)

**Граф:**
```
ИВАН (Ch3): Скрывает красную глину
  ↓
МАРИЯ: Подозрение, trust 3→1
  ↓ (Ch5)
МАРИЯ: Проверяет отчёты, trust 1→-1
  ↓ (Ch7)
МАРИЯ: Отказывает в помощи
  ↓ (Ch8)
ИВАН: В ловушке
  ↓ (Ch9)
МАРИЯ: Спасает (вина), trust -1→+2
  ↓ (Ch12)
Совместно против культа, trust +2→+5, романтика
```

---

## 🔧 ТИПЫ РЕЗОНАНСОВ

**1. EMOTIONAL:** Действие → Эмоция → Решение  
**2. MORAL:** Действие → Дилемма → Выбор  
**3. PRACTICAL:** Действие → Обстоятельства → Новые возможности  
**4. ROMANTIC:** Действие → Близость → Chemistry

---

## 📈 TRACKING SYSTEM

**Файл: resonance_graph.json**
```json
{
  "resonance_events": [...],
  "trust_tracker": {
    "ivan_maria": {"current": 5, "history": [...]}
  },
  "unresolved_ripples": [...],
  
  "causality_graph": {
    "nodes": [
      {
        "id": "event_001",
        "chapter": 3,
        "type": "action",
        "description": "Иван скрывает улику",
        "why_happened": [
          "Боится раскрыть своё прошлое",
          "Не доверяет Марии полностью",
          "Улика компрометирует его семью"
        ],
        "what_changed": [
          "Trust Мария→Иван: -2",
          "Subplot 'Тайна Ивана': activated",
          "Мария начинает наблюдение"
        ],
        "mandatory_setup": [
          "✅ Ch1: Установлено что Иван скрытен",
          "✅ Ch2: Намёк на тёмное прошлое",
          "❌ MISSING: Мотивация скрывать от Марии (plot hole!)"
        ]
      },
      {
        "id": "event_005",
        "chapter": 7,
        "type": "decision",
        "description": "Мария отказывает Ивану в помощи",
        "why_happened": [
          "Накопленное недоверие (event_001)",
          "Обнаружила его ложь (event_003)",
          "Собственная гордость"
        ],
        "what_changed": [
          "Иван попадает к антагонисту",
          "Subplot 'Раскол': peak",
          "Maria guilt: +5 (setup для Ch9)"
        ],
        "mandatory_setup": [
          "✅ event_001: Недоверие создано",
          "✅ event_003: Ложь обнаружена",
          "✅ Ch6: Мария эмоционально ранена"
        ]
      }
    ],
    "edges": [
      {
        "from": "event_001",
        "to": "event_005",
        "type": "emotional_causality",
        "reason": "Скрытая улика → недоверие → отказ помочь",
        "strength": 0.85,
        "inevitability": "high",
        "alternative_paths": [
          "Если бы Иван признался (Ch4) → Мария бы простила"
        ]
      }
    ],
    "plot_holes": [
      {
        "node": "event_001",
        "issue": "Нет установленной причины скрывать улику от Марии",
        "severity": "medium",
        "fix_suggestions": [
          "Добавить в Ch1-2: Иван боится что Мария отвергнет его семью",
          "Или: Иван связан клятвой молчания"
        ]
      },
      {
        "node": "event_010",
        "issue": "Персонаж знает информацию без источника",
        "severity": "critical",
        "fix_suggestions": [
          "Добавить сцену где информация передаётся",
          "Или: объяснить как персонаж узнал"
        ]
      }
    ],
    "orphaned_nodes": [
      {
        "node": "event_012",
        "issue": "Событие без причины (no incoming edges)",
        "description": "Антагонист внезапно знает слабость героя"
      }
    ]
  }
}
```

---

## 🕸️ NARRATIVE CAUSALITY GRAPH

**НОВОЕ В v3.0:** Полный граф причин и следствий

### Зачем нужен граф?

**Проблема:** События происходят потому что "так надо сюжету"  
**Решение:** Каждое событие имеет ПРИЧИНУ и ПОСЛЕДСТВИЕ

### Структура графа

**NODES (Узлы) = События**
- `type`: action/revelation/decision/turning_point
- `why_happened`: список причин (ОБЯЗАТЕЛЬНО!)
- `what_changed`: список последствий
- `mandatory_setup`: что должно быть установлено ДО

**EDGES (Рёбра) = Причинные связи**
- `from` → `to`: какое событие вызвало какое
- `reason`: объяснение связи
- `strength`: 0.0-1.0 (насколько сильна связь)
- `inevitability`: low/medium/high

### Автоматическая детекция проблем

**1. PLOT HOLES (Дыры в сюжете)**
```
Событие без достаточной мотивации
→ "Почему персонаж так поступил?"
→ Добавь setup ИЛИ измени событие
```

**2. ORPHANED NODES (Сирот-события)**
```
Событие без входящих связей
→ Появилось из ниоткуда
→ Добавь причину ИЛИ удали
```

**3. DEAD ENDS (Тупики)**
```
Событие без исходящих связей
→ Ничего не изменило
→ Либо добавь последствия, либо событие лишнее
```

### Визуализация графа

```
python visualize_causality.py

OUTPUT:
┌─────────────────────────────────────────┐
│     NARRATIVE CAUSALITY GRAPH          │
└─────────────────────────────────────────┘

event_001 [Ch3: Иван скрывает улику]
  │
  ├──→ event_003 (strength: 0.7)
  │    "Мария проверяет отчёты"
  │
  └──→ event_005 (strength: 0.85)
       "Мария отказывает в помощи"
         │
         └──→ event_008 (strength: 0.9)
              "Иван попадает к антагонисту"

⚠️  PLOT HOLE обнаружен: event_001
    Missing motivation: почему скрывать от Марии?

❌ ORPHAN NODE: event_012
    No incoming edges (событие без причины)
```

### Использование в работе

**ШАГ 1: После планирования сюжета**
```bash
python build_causality_graph.py outline.md

РЕЗУЛЬТАТ: causality_graph.json с базовыми узлами
```

**ШАГ 2: После каждой главы**
```bash
python update_causality.py --chapter 5

ПРОВЕРКИ:
✅ Все события имеют причины?
✅ Setup для событий сделан заранее?
❌ Plot holes обнаружены?
```

**ШАГ 3: Перед финалом**
```bash
python validate_causality.py --full

ОТЧЁТ:
- Orphaned nodes: 2 (критично!)
- Plot holes: 3 medium, 1 critical
- Dead ends: 5 (события ни к чему не ведут)
- Fork points: 7 (где сюжет мог пойти иначе)
```

---

## ✅ ЧЕКЛИСТ

```
[ ] Кто затронут действием?
[ ] Какая эмоция у затронутого?
[ ] Как изменится trust?
[ ] Когда проявится ripple? (через сколько глав)
[ ] Какое решение примет затронутый?
[ ] Есть ли волны 3-го уровня?
[ ] Когда разрешится конфликт?
```

---

## 💡 ЗОЛОТЫЕ ПРАВИЛА

1. Каждое важное действие → минимум 1 ripple
2. Минимум 3 волны резонанса
3. Trust меняется постепенно
4. Резонанс = характер персонажа
5. Отслеживай незакрытые ripples
6. Длинные цепи (5+ глав) = глубина

---

## 🔥 ENHANCED: NARRATIVE CAUSALITY GRAPH

**Добавлено в v3.0 ENHANCED**

### Назначение:
Формализованный граф событий с автоматической детекцией plot holes и визуализацией причинно-следственных связей.

---

### СТРУКТУРА CAUSALITY GRAPH

**Файл:** `resonance_graph.json`

```json
{
  "meta": {
    "story": "Detective Fantasy Project",
    "total_nodes": 47,
    "total_edges": 89,
    "plot_holes_detected": 2,
    "last_validated": "2025-03-15"
  },
  
  "nodes": [
    {
      "id": "event_001",
      "chapter": 3,
      "type": "action",
      "description": "Иван скрывает улику от Марии",
      
      "why_happened": {
        "surface_reason": "Боится что улика скомпрометирует его",
        "deep_reason": "Защищает старого друга",
        "character_state": "Лояльность > Правосудие (в этот момент)"
      },
      
      "what_changed": {
        "world_state": "Улика потеряна для следствия",
        "relationships": ["Trust Мария→Иван -2"],
        "subplot_impact": "Subplot 'предательство' +1 stage"
      },
      
      "validation": {
        "has_motivation": true,
        "character_can_do_this": true,
        "no_contradictions": true
      }
    },
    
    {
      "id": "event_005",
      "chapter": 7,
      "type": "decision",
      "description": "Мария отказывает Ивану в помощи",
      
      "why_happened": {
        "surface_reason": "Слишком занята своим делом",
        "deep_reason": "Подсознательная месть за скрытую улику",
        "caused_by_events": ["event_001"]
      },
      
      "what_changed": {
        "relationships": ["Ivan_feelings: обида +2", "Maria: guilt +1"],
        "plot_impact": "Иван вынужден искать помощь у антагониста"
      },
      
      "validation": {
        "has_motivation": true,
        "logical_from_event_001": true
      }
    },
    
    {
      "id": "event_010",
      "chapter": 12,
      "type": "revelation",
      "description": "Персонаж C узнаёт о тайне без видимой причины",
      
      "why_happened": {
        "surface_reason": "???",
        "deep_reason": "NOT ESTABLISHED",
        "caused_by_events": []
      },
      
      "what_changed": {
        "plot_impact": "Критическая информация для развязки"
      },
      
      "validation": {
        "has_motivation": false,
        "plot_hole_detected": true,
        "severity": "critical",
        "issue": "Нет источника информации. КАК персонаж узнал?"
      }
    }
  ],
  
  "edges": [
    {
      "id": "edge_001_to_005",
      "from": "event_001",
      "to": "event_005",
      "reason": "Скрытая улика → недоверие → отказ помочь",
      "delay_chapters": 4,
      "strength": 8,
      "inevitability": 0.7
    },
    {
      "id": "edge_005_to_015",
      "from": "event_005",
      "to": "event_015",
      "reason": "Отказ Марии → Иван идёт к антагонисту → Попадает в ловушку",
      "delay_chapters": 5,
      "strength": 9,
      "inevitability": 0.85
    }
  ],
  
  "plot_holes": [
    {
      "node": "event_010",
      "issue": "Персонаж знает информацию без источника",
      "severity": "critical",
      "detected_at": "validation_pass_2",
      "suggestions": [
        "Добавить сцену где персонаж подслушивает",
        "Ввести информатора",
        "Персонаж находит документ"
      ]
    },
    {
      "node": "event_023",
      "issue": "Мотивация слишком слабая для такого решения",
      "severity": "major",
      "suggestion": "Усилить мотивацию в главах 10-11"
    }
  ],
  
  "causality_chains": [
    {
      "chain_id": "betrayal_to_redemption",
      "description": "От предательства Ивана до его искупления",
      "nodes": ["event_001", "event_005", "event_015", "event_028", "event_045"],
      "strength": "strong",
      "payoff_chapter": 45,
      "reader_satisfaction_projected": 0.88
    }
  ]
}
```

---

### ВИЗУАЛИЗАЦИЯ ГРАФА

**ASCII представление:**

```
ГЛАВА 3 [event_001: Иван скрывает улику]
           │
           │ (недоверие нарастает)
           ↓
ГЛАВА 7 [event_005: Мария отказывает помочь]
           │
           │ (Иван вынужден...)
           ↓
ГЛАВА 12 [event_015: Иван обращается к антагонисту]
           │
           │ (ловушка)
           ↓
ГЛАВА 18 [event_028: Иван попадает в западню]
           │
           │ (осознание)
           ↓
ГЛАВА 24 [event_045: Иван жертвует собой для Марии]
           │
           └─→ REDEMPTION ARC COMPLETE
```

---

### АВТОМАТИЧЕСКАЯ ВАЛИДАЦИЯ

**Запускается после каждой главы:**

```python
def validate_causality_graph(graph):
    errors = []
    
    # Проверка 1: Каждое событие имеет причину
    for node in graph.nodes:
        if node.type in ["decision", "revelation"]:
            if not node.why_happened.caused_by_events:
                if not node.why_happened.deep_reason:
                    errors.append({
                        "node": node.id,
                        "error": "NO MOTIVATION",
                        "severity": "critical"
                    })
    
    # Проверка 2: Edges логичны
    for edge in graph.edges:
        from_node = graph.get_node(edge.from)
        to_node = graph.get_node(edge.to)
        
        if edge.inevitability > 0.9:
            # Если неизбежность высока, должна быть ПРЯМАЯ связь
            if to_node.chapter - from_node.chapter > 10:
                errors.append({
                    "edge": edge.id,
                    "error": "HIGH INEVITABILITY but TOO MUCH DELAY",
                    "suggestion": "Either reduce delay OR reduce inevitability"
                })
    
    # Проверка 3: Orphan nodes (события без последствий)
    for node in graph.nodes:
        outgoing_edges = graph.get_edges_from(node.id)
        if len(outgoing_edges) == 0 and node.chapter < (total_chapters - 5):
            errors.append({
                "node": node.id,
                "error": "ORPHAN NODE - no consequences",
                "severity": "major",
                "suggestion": "Add ripple effects OR remove event"
            })
    
    return errors
```

---

### ТЕПЛОВАЯ КАРТА НАПРЯЖЕНИЯ

**Показывает интенсивность причинно-следственных связей:**

```
CHAPTERS:  3    7    12   18   24   30   35   40   45
           │    │    │    │    │    │    │    │    │
INTENSITY: ██   ███  █    ████ ██   █    ███  █    █████
           │    │    │    │    │    │    │    │    │
ANALYSIS:  ok   ok   low! high ok   low  ok   low  CLIMAX

WARNINGS:
- Chapter 12: Низкая интенсивность (pacing sag)
  → Рекомендация: Добавить событие или усилить существующее
  
- Chapter 18: Высокая интенсивность (4 крупных события)
  → Рекомендация: Распределить на 2 главы для лучшего pacing
```

---

### ДИАГНОСТИКА PLOT HOLES

**Автоматические проверки:**

1. **Информационный парадокс:**
```
ОБНАРУЖЕНО: Персонаж C знает о тайне X
ПРОВЕРКА источников:
  - Кто мог рассказать? → Только A и B
  - Сцена с A? → Нет
  - Сцена с B? → Нет
  - Документ? → Нет
ВЕРДИКТ: PLOT HOLE → Добавить источник информации
```

2. **Мотивационный пробел:**
```
СОБЫТИЕ: Персонаж Y предаёт союзников
МОТИВАЦИЯ установленная: "Жадность"
ПРОВЕРКА силы:
  - Предательство риск: 9/10 (смерть если раскроют)
  - Награда: 2/10 (небольшая сумма)
  - Risk/Reward ratio: НЕСООТВЕТСТВИЕ
ВЕРДИКТ: Мотивация слабая → Усилить награду ИЛИ добавить доп. мотивацию
```

---

### ИСПОЛЬЗОВАНИЕ В НАПИСАНИИ

**ПЕРЕД ГЛАВОЙ:**
```
ТЫ: "Пишу главу 15, где Мария узнаёт правду об Иване"

КЛОД проверяет граф:
- Предшествующие события: event_001, event_005, event_010
- Логическая цепь: Скрытая улика → Подозрения → Расследование → Раскрытие
- Validation: ✓ Есть путь к этой информации
- Emotional state: Мария готова к конфронтации (grief stage 4)

РЕКОМЕНДАЦИЯ:
"Цепь событий логична. Мария имеет мотивацию и средства узнать правду.
EMOTIONAL PAYOFF будет высоким (reader ждали этого с главы 7).
PROCEED."
```

**ПОСЛЕ ГЛАВЫ:**
```
ДОБАВЛЯЮ в граф:

{
  "id": "event_052",
  "chapter": 15,
  "type": "revelation",
  "description": "Мария узнаёт что Иван скрывал улику",
  
  "why_happened": {
    "caused_by_events": ["event_001", "event_005", "event_010"],
    "investigation_path": "Документы → Свидетель → Вещдок"
  },
  
  "what_changed": {
    "relationships": ["Trust Мария→Иван: 3 → 0 (РАЗРУШЕНО)"],
    "subplot": "Предательство достигло пика",
    "character_arcs": ["Мария: disillusionment complete"]
  },
  
  "ripple_effects_predicted": [
    "Ch17: Мария конфронтует Ивана",
    "Ch20: Иван начинает искупление",
    "Ch24: Финальная жертва Ивана"
  ]
}

EDGES созданы автоматически:
- event_052 → event_055 (конфронтация)
- event_052 → event_060 (искупление начинается)
```

---

### МЕТРИКИ КАЧЕСТВА

```json
{
  "causality_graph_score": 92,
  
  "breakdown": {
    "motivation_strength": 95,
    "logical_consistency": 98,
    "orphan_nodes": 2,
    "plot_holes": 1,
    "causality_density": "optimal",
    "payoff_setup_ratio": 0.87
  },
  
  "strengths": [
    "Все ключевые события имеют сильную мотивацию",
    "Длинные цепи причинно-следствий (читатель ЧУВСТВУЕТ логику)",
    "Хороший баланс setup/payoff"
  ],
  
  "issues": [
    {
      "issue": "2 orphan nodes (события без последствий)",
      "severity": "minor",
      "fix": "Добавить ripple effects ИЛИ удалить события"
    },
    {
      "issue": "1 plot hole (информационный парадокс)",
      "severity": "major",
      "fix": "Добавить источник информации в Ch10"
    }
  ]
}
```

---

### ADVANCED: FORK POINTS

**Моменты где сюжет мог пойти иначе:**

```json
{
  "fork_points": [
    {
      "event": "event_005: Мария отказывает Ивану",
      "alternative_path": "Мария помогает Ивану",
      "consequences_if_alternative": {
        "positive": "Иван не попадает к антагонисту",
        "negative": "Нет redemption arc, история скучнее",
        "reader_satisfaction": -15
      },
      "why_chosen_path_better": "Конфликт глубже, emotional payoff сильнее"
    }
  ]
}
```

---

**РЕЗУЛЬТАТ ENHANCED VERSION:** 
- Каждое событие имеет ПРИЧИНУ
- Каждая причина ведёт к ПОСЛЕДСТВИЯМ
- Plot holes детектируются автоматически
- Граф визуализирует всю логику истории

**УРОВЕНЬ:** Professional story architecture

---

**Конец модуля: Cross-Character Resonance System**

---

## ## MINI (QUICK режим — суть за 10 строк)

**Резонанс = действие А меняет решение Б, что влияет на судьбу В.** Персонажи — не острова.

**Три типа резонанса:**
1. **Доверие:** событие повышает или понижает trust между двумя персонажами (измеримо).
2. **Цепная реакция:** А сделал → Б изменил поведение → В пострадал или выиграл.
3. **Накопленный долг:** персонаж помог раньше — это возвращается позже.

**Как применить к главе:**
Перед написанием: кто с кем в этой сцене? Что изменится в их отношениях после?
Trust повышается через: уязвимость, выполненное обещание, жертву.
Trust падает через: ложь (даже обнаруженную позже), предательство приоритетов, молчание когда нужно было говорить.

**Красный флаг:** персонажи в финале относятся друг к другу так же как в начале — резонанса не было.
**Правило на главу:** один сдвиг в одних отношениях. Конкретно — в какую сторону и почему.
