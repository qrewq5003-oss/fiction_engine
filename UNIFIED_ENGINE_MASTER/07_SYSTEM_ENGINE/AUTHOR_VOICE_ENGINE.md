# 🎤 AUTHOR VOICE ENGINE v3.0

**Файл:** system/AUTHOR_VOICE_ENGINE.md  
**Версия:** 3.0.0  
**Рейтинг:** 5++/5  
**Назначение:** Изучение и сохранение уникального авторского стиля

---

## 🎯 ФИЛОСОФИЯ

**Проблема:** AI пишет в "среднем" стиле, теряя уникальность автора.

**Решение:** Система изучает примеры текста автора и адаптирует все модули под его голос.

**Принцип:** Автор → Анализ → Профиль → Адаптация всех движков.

---

## 📊 АНАТОМИЯ ГОЛОСА АВТОРА

```yaml
author_voice_profile:
  name: "Stephen King Style"
  
  syntax:
    avg_sentence_length: 12.3  # слова
    sentence_variety: high
    complex_sentences: 0.25
    fragments: 0.15  # "But still. She waited."
    
  vocabulary:
    lexical_diversity: 0.72
    colloquial_ratio: 0.6  # много разговорных слов
    archaic_usage: 0.02  # почти нет
    profanity: 0.08  # есть мат
    unique_words: ["ayuh", "thinnies", "ka"]
    
  rhythm:
    pacing_preference: "variable"  # от медленного к быстрому
    paragraph_length: short-medium
    dialogue_ratio: 0.45  # много диалогов
    description_density: medium
    
  dialogue_style:
    formality: low
    dialect_usage: high
    interruptions: frequent
    subtext_level: high
    speech_tags: minimal  # "said" доминирует
    
  imagery:
    metaphor_frequency: high
    metaphor_type: "everyday_objects"  # обыденные вещи
    simile_ratio: 0.35
    sensory_focus: [visual: 0.4, auditory: 0.3, olfactory: 0.2]
    
  tone:
    darkness: 0.7
    humor_type: "dark_ironic"
    intimacy: high  # прямое обращение к читателю
    nostalgia: 0.6
    
  structure_preferences:
    flashbacks: frequent
    time_jumps: occasional
    multiple_povs: yes
    interludes: rare
    
  signature_techniques:
    - "Stream of consciousness moments"
    - "Pop culture references (1950s-1980s)"
    - "Direct reader address"
    - "Small town settings"
    - "Ordinary people in extraordinary situations"
```

---

## 🔬 ПРОЦЕСС АНАЛИЗА

### ШАГ 1: Загрузка примеров

```python
def learn_from_samples(author_texts):
    """Анализирует 3-5 глав текста автора"""
    
    profile = {}
    
    # Синтаксис
    sentences = extract_sentences(author_texts)
    profile['syntax'] = {
        'avg_length': np.mean([len(s.split()) for s in sentences]),
        'variety': np.std([len(s.split()) for s in sentences]),
        'fragments': count_fragments(sentences) / len(sentences)
    }
    
    # Лексика
    words = extract_words(author_texts)
    profile['vocabulary'] = {
        'diversity': len(set(words)) / len(words),
        'unique_words': find_unique_words(words),
        'colloquial_ratio': count_colloquial(words) / len(words)
    }
    
    # Диалоги
    dialogues = extract_dialogues(author_texts)
    profile['dialogue'] = {
        'ratio': len(dialogue_words) / len(words),
        'speech_tags': analyze_speech_tags(dialogues),
        'formality': measure_formality(dialogues)
    }
    
    return profile
```

---

### ШАГ 2: Создание профиля

```python
def create_voice_profile(analysis):
    """Создаёт применимый профиль"""
    
    profile = {
        # HARD RULES (обязательные)
        'hard_rules': [
            f"Avg sentence length: {analysis.syntax.avg_length} ± 2 words",
            f"Use dialogue {analysis.dialogue.ratio*100}% of text",
            f"Speech tags: prefer '{analysis.dialogue.primary_tag}'"
        ],
        
        # SOFT GUIDELINES (рекомендации)
        'soft_rules': [
            f"Metaphor type: {analysis.imagery.metaphor_type}",
            f"Tone: {analysis.tone.darkness} darkness scale",
            f"Humor: {analysis.tone.humor_type}"
        ],
        
        # FORBIDDEN (запреты)
        'forbidden': [
            "Archaic language" if analysis.vocabulary.archaic < 0.05,
            "Formal dialogue" if analysis.dialogue.formality < 0.3,
            "Long descriptions" if analysis.description_density < 0.3
        ],
        
        # SIGNATURE MOVES (фирменные приёмы)
        'signatures': analysis.signature_techniques
    }
    
    return profile
```

---

## 🎛️ ПРИМЕНЕНИЕ К ДВИЖКАМ

### Адаптация всех 25 модулей

```python
def apply_voice_to_engines(voice_profile):
    """Модифицирует параметры движков под голос автора"""
    
    # 15_dialogue_style
    dialogue_style.override({
        'speech_tag_preference': voice_profile.dialogue.primary_tag,
        'formality': voice_profile.dialogue.formality,
        'interruptions': voice_profile.dialogue.interruptions
    })
    
    # 23_literary_craft
    literary_craft.override({
        'metaphor_type': voice_profile.imagery.metaphor_type,
        'sensory_focus': voice_profile.imagery.sensory_focus
    })
    
    # 24_artistic_foundation
    artistic_foundation.override({
        'sentence_length_target': voice_profile.syntax.avg_length,
        'rhythm_style': voice_profile.rhythm.pacing_preference
    })
    
    # 12_pacing_engine
    pacing_engine.override({
        'dialogue_ratio_target': voice_profile.dialogue.ratio,
        'description_density': voice_profile.rhythm.description_density
    })
    
    # META_RULES.yaml
    meta_rules.add_override({
        'priority': 100,  # ВЫСШИЙ ПРИОРИТЕТ
        'source': 'AUTHOR_VOICE_ENGINE',
        'rules': voice_profile.hard_rules
    })
```

---

## 📈 ПРИМЕРЫ АДАПТАЦИИ

### ПРИМЕР 1: Stephen King vs Brandon Sanderson

```yaml
stephen_king_output:
  "The door was open. That wasn't right. He'd locked it. He always locked it.
  
  Tommy stepped inside, hand on the light switch, breath coming hard. The smell hit him first—old pennies and meat gone bad. Jesus. What the hell?
  
  'Hello?' His voice cracked. Kid's voice. He hated that.
  
  Nothing. Just the tick-tick of the kitchen clock. Loud as a bomb.
  
  Then he saw it."

brandon_sanderson_output:
  "The door stood open, its hinges gleaming with the faint blue light that marked Allomancy at work. Tommy paused, burning tin to enhance his senses. The metallic scent was wrong—not copper or bronze, but something else. Something older.
  
  He'd locked this door. The lock was Invested, bound with a Hemalurgic spike keyed to his own soul. No one should have been able to open it without triggering the wards.
  
  Unless they had a metalmind. Or unless the Door itself had been compromised.
  
  Tommy stepped forward, drawing on his steel reserves. If this was a trap, he'd need to be ready."
```

**Различия:**
- King: короткие фразы, разговорный тон, сенсорика (запах)
- Sanderson: длинные предложения, магическая терминология, системность

---

### ПРИМЕР 2: Применение профиля Hemingway

```yaml
hemingway_profile:
  syntax:
    avg_sentence_length: 8.5
    complex_sentences: 0.05
    fragments: 0.30
    
  vocabulary:
    simple_words: 0.85
    colloquial: 0.60
    no_adverbs: true
    
  style:
    "iceberg_theory": true  # показывай 1/8, остальное под водой
    "objectivity": high
    "emotion": implicit  # не называй, покажи
```

**Результат:**

```
The man sat. Coffee was cold. He didn't drink it.

Through the window, rain. Gray street. Empty.

She was gone. That was that.

He stood. Left money on the table. More than enough.

Outside, rain on his face. He didn't wipe it.
```

---

## 🔄 CONTINUOUS LEARNING

```python
def update_voice_profile(new_chapter, current_profile):
    """Обновляет профиль на основе новых текстов"""
    
    new_analysis = analyze_text(new_chapter)
    
    # Обновление с весом 0.1 (90% старое, 10% новое)
    updated_profile = blend_profiles(
        current_profile, 
        new_analysis,
        weight_old=0.9,
        weight_new=0.1
    )
    
    return updated_profile
```

---

## 🎯 РЕЖИМ "КАК Я ПИШУ"

```python
@command("напиши как я")
def author_voice_mode():
    """Активирует голос автора"""
    
    # Приоритет #1 - голос автора
    ENGINE_CONTROLLER.set_mode('AUTHOR_VOICE_MODE')
    
    # Все модули подчиняются профилю
    for engine in ALL_ENGINES:
        engine.apply_voice_override(AUTHOR_VOICE_PROFILE)
    
    # META_RULES адаптируются
    META_RULES.priority = 90  # ниже голоса автора (100)
    
    return "Author voice mode ACTIVE"
```

---

## 📊 МЕТРИКИ КАЧЕСТВА

```json
{
  "voice_match_score": 0.87,  # насколько близко к оригиналу
  
  "matching_metrics": {
    "sentence_length": 0.92,
    "vocabulary_similarity": 0.85,
    "dialogue_style": 0.89,
    "rhythm": 0.84,
    "tone": 0.86
  },
  
  "deviations": [
    {
      "metric": "metaphor_frequency",
      "expected": 0.35,
      "actual": 0.42,
      "deviation": +0.07,
      "severity": "minor"
    }
  ]
}
```

---

## 🌟 ИТОГ

AUTHOR_VOICE_ENGINE — самый мощный модуль системы.

**Он превращает AI из подражателя в продолжение автора.**

Текст становится **неотличимым** от оригинала.

---

**СТАТУС:** ✅ VOICE MASTERY READY
