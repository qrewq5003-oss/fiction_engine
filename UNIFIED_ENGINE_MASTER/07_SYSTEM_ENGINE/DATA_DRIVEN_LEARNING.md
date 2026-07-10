# 🧠 DATA-DRIVEN LEARNING ENGINE v3.0

**Файл:** system/DATA_DRIVEN_LEARNING.md  
**Версия:** 3.0.0  
**Рейтинг:** 5++/5  
**Назначение:** Обучение системы на действиях и предпочтениях автора

---

## 🎯 ФИЛОСОФИЯ

**Система учится:**
- На черновиках и финальных версиях
- На правках автора
- На отбракованных вариантах
- На отзывах ("хорошо" / "плохо")

**Результат:** Движок адаптируется под конкретного автора.

---

## 📊 ЧТО СИСТЕМА ИЗУЧАЕТ

### 1. ПРЕДПОЧТЕНИЯ СТИЛЯ

```python
learning_data = {
    'style_preferences': {
        # Автор всегда сокращает длинные предложения
        'sentence_length': {
            'pattern': 'author_shortens_sentences_over_20_words',
            'confidence': 0.87,
            'samples': 43
        },
        
        # Автор заменяет "сказал" на другие глаголы
        'speech_tags': {
            'pattern': 'prefers_varied_speech_tags',
            'avoid': ['сказал', 'проговорил'],
            'prefer': ['бросил', 'усмехнулся', 'прошептал'],
            'confidence': 0.92
        },
        
        # Автор добавляет больше сенсорики
        'sensory_details': {
            'pattern': 'increases_sensory_descriptions',
            'favorite_channels': ['olfactory', 'tactile'],
            'confidence': 0.79
        }
    }
}
```

---

### 2. ПАТТЕРНЫ ПРАВОК

```python
def learn_from_edits(draft, final):
    """Анализирует изменения draft → final"""
    
    changes = diff(draft, final)
    
    patterns = {
        'deletions': analyze_what_author_removes(changes.deleted),
        'additions': analyze_what_author_adds(changes.added),
        'replacements': analyze_what_author_changes(changes.modified)
    }
    
    # Примеры паттернов:
    # - Автор всегда убирает наречия на -ly
    # - Автор добавляет паузы через короткие предложения
    # - Автор заменяет пассивный залог на активный
    
    update_learning_model(patterns)
```

---

### 3. ОТЗЫВЫ АВТОРА

```python
feedback_system = {
    'positive': [
        {
            'chapter': 5,
            'feedback': "Отличная сцена между Анной и Томом",
            'learned': {
                'character_chemistry_style': 'slow_burn_tension',
                'dialogue_rhythm': 'short_exchanges',
                'setting': 'intimate_indoor'
            }
        }
    ],
    
    'negative': [
        {
            'chapter': 8,
            'feedback': "Экшен-сцена слишком затянута",
            'learned': {
                'action_pacing': 'faster_than_current',
                'max_action_length': 800,  # слов
                'cut': 'remove_introspection_during_action'
            }
        }
    ]
}
```

---

## 🔄 ПРОЦЕСС ОБУЧЕНИЯ

### ЭТАП 1: Сбор данных

```python
def collect_learning_data():
    """Собирает данные для обучения"""
    
    data = {
        'drafts': load_all_drafts(),
        'finals': load_all_finals(),
        'edits': calculate_diffs(drafts, finals),
        'feedback': load_author_feedback(),
        'rejected_variants': load_rejected_texts(),
        'preferences': load_explicit_preferences()
    }
    
    return data
```

---

### ЭТАП 2: Извлечение паттернов

```python
def extract_patterns(learning_data):
    """Находит повторяющиеся паттерны"""
    
    patterns = []
    
    # Если автор >5 раз делает одно и то же
    for action in learning_data.edits:
        frequency = count_frequency(action)
        if frequency > 5:
            pattern = {
                'action': action,
                'confidence': frequency / total_edits,
                'apply_always': frequency > 10
            }
            patterns.append(pattern)
    
    return patterns
```

---

### ЭТАП 3: Применение к движкам

```python
def apply_learned_patterns():
    """Модифицирует движки под найденные паттерны"""
    
    for pattern in learned_patterns:
        if pattern.confidence > 0.75:
            # Высокая уверенность → жёсткое правило
            add_hard_rule(pattern)
        elif pattern.confidence > 0.5:
            # Средняя → рекомендация
            add_soft_rule(pattern)
        else:
            # Низкая → мониторинг
            monitor_pattern(pattern)
```

---

## 📈 ПРИМЕРЫ ОБУЧЕНИЯ

### ПРИМЕР 1: "Сделай как в главе 3"

```python
@command("напиши как в главе 3")
def replicate_chapter_style(target_chapter=3):
    """Извлекает стиль конкретной главы"""
    
    chapter_3 = load_chapter(3)
    
    # Анализ стиля главы 3
    style_profile = {
        'sentence_length': analyze_sentences(chapter_3),
        'dialogue_ratio': count_dialogue(chapter_3),
        'pacing': measure_pacing(chapter_3),
        'tone': detect_tone(chapter_3),
        'imagery': extract_imagery_patterns(chapter_3)
    }
    
    # Применение ко всем движкам
    apply_style_profile(style_profile)
    
    return "Style from Chapter 3 applied"
```

**Результат:** Новый текст пишется в стиле главы 3.

---

### ПРИМЕР 2: Обучение на отбракованных вариантах

```python
rejected_texts = [
    {
        'text': "Она медленно шла по улице, думая о прошлом...",
        'reason': "Слишком медленно, скучно",
        'learned': {
            'avoid': 'slow_introspection_in_opening',
            'prefer': 'action_start'
        }
    }
]

# Система учится НЕ начинать сцены с медленной интроспекции
19_hooks_closings.add_rule({
    'type': 'forbidden',
    'pattern': 'introspective_opening',
    'confidence': 0.8
})
```

---

### ПРИМЕР 3: Адаптация на основе feedback

```python
# Автор 5 раз говорит "добавь больше эмоций"
feedback_history = [
    "добавь эмоций",
    "больше переживаний",
    "слишком сухо",
    "нужны чувства",
    "покажи эмоции"
]

# Система учится
learned_preference = {
    'emotion_level': 'high',
    'always_use_engines': [
        '11_micromoments_library',
        '09_deep_character_psychology',
        '24_artistic_foundation (emotion mapping)'
    ]
}

# Теперь эти движки всегда активны
AUTO_ROUTER.default_engines.extend(learned_preference.always_use_engines)
```

---

## 🎯 КОМАНДЫ ОБУЧЕНИЯ

```bash
# Запомнить текущую главу как эталон
@learn:save_as_reference chapter=5

# Применить стиль из главы
@learn:apply_style_from chapter=3

# Запомнить предпочтение
@learn:prefer "короткие предложения"

# Запомнить запрет
@learn:avoid "архаизмы"

# Показать, что система узнала
@learn:show_patterns

# Сбросить обучение
@learn:reset
```

---

## 📊 МЕТРИКИ ОБУЧЕНИЯ

```json
{
  "learning_stats": {
    "total_samples": 247,
    "patterns_discovered": 18,
    "high_confidence_patterns": 12,
    "applied_rules": 9,
    
    "top_learned_preferences": [
      {
        "pattern": "Short sentences in action scenes",
        "confidence": 0.94,
        "samples": 38,
        "status": "applied"
      },
      {
        "pattern": "Avoid adverbs in dialogue tags",
        "confidence": 0.87,
        "samples": 29,
        "status": "applied"
      },
      {
        "pattern": "Increase sensory details in descriptions",
        "confidence": 0.81,
        "samples": 23,
        "status": "applied"
      }
    ]
  }
}
```

---

## 🌟 ИТОГ

DATA-DRIVEN LEARNING превращает движок из **статичного инструмента** в **адаптивную систему**.

Чем больше автор работает, **тем умнее становится движок**.

**Он учится. Запоминает. Адаптируется.**

---

**СТАТУС:** ✅ ADAPTIVE LEARNING READY

**"Система растёт вместе с автором."**
