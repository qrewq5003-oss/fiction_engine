# 🔍 MEMORY VALIDATOR v3.0

**Файл:** system/MEMORY_VALIDATOR.md  
**Версия:** 3.0.0  
**Рейтинг:** 5+/5  
**Назначение:** Автоматическая проверка целостности и непротиворечивости памяти проекта

---

## 🎯 ФУНКЦИИ

### 1. ПРОВЕРКА ПЕРСОНАЖЕЙ

```python
def validate_characters():
    """Проверяет непротиворечивость персонажей"""
    
    checks = {
        'age_consistency': check_age_timeline(),
        'appearance_changes': check_physical_consistency(),
        'personality_drift': check_character_voice(),
        'relationship_logic': check_relationships(),
        'arc_progress': check_character_arcs(),
        'death_resurrection': check_alive_status()
    }
    
    return issues
```

**Примеры ошибок:**
- Персонаж в главе 3 — 25 лет, в главе 10 — 23 года
- Описан как блондин в ch01, брюнет в ch15
- Умер в ch08, говорит в ch12
- Арка завершена в ch10, но персонаж не изменился

---

### 2. ПРОВЕРКА ВРЕМЕННОЙ ЛИНИИ

```python
def validate_timeline():
    """Проверяет логику времени"""
    
    issues = []
    
    # Хронология событий
    for event in timeline.events:
        if event.date_before(event.dependencies):
            issues.append(f"Event {event.id} happens before its cause")
    
    # Путешествия
    for scene in scenes:
        travel_time = calculate_travel(scene.location_from, scene.location_to)
        if scene.time_elapsed < travel_time:
            issues.append(f"Impossible travel speed in scene {scene.id}")
    
    # Возраст персонажей
    for char in characters:
        if char.age_at(scene.time) < 0:
            issues.append(f"{char.name} not yet born in scene {scene.id}")
    
    return issues
```

---

### 3. ПРОВЕРКА СЮЖЕТНЫХ АРОК

```python
def validate_plot_arcs():
    """Проверяет завершённость арок"""
    
    for arc in plot_arcs:
        # Setup без payoff
        if arc.has_setup and not arc.has_resolution:
            warn(f"Arc '{arc.name}' set up but never resolved")
        
        # Payoff без setup
        if arc.has_resolution and not arc.has_setup:
            error(f"Arc '{arc.name}' resolved without setup")
        
        # Забытые подсюжеты
        if arc.last_mentioned_chapter < current_chapter - 5:
            warn(f"Arc '{arc.name}' forgotten for {chapters_since} chapters")
```

---

### 4. ПРОВЕРКА МАГИЧЕСКОЙ СИСТЕМЫ (для фэнтези)

```python
def validate_magic_system():
    """Проверяет логику магии"""
    
    rules = magic_system.rules
    
    for scene in magic_scenes:
        spell_used = scene.magic_used
        
        # Проверка ограничений
        if spell_used.cost > character.mana_at(scene.time):
            error(f"Not enough mana for {spell_used.name}")
        
        # Проверка правил
        if spell_used.element in character.forbidden_elements:
            error(f"{character.name} can't use {spell_used.element}")
        
        # Проверка последствий
        if spell_used.requires_sacrifice and not scene.has_sacrifice:
            error(f"Spell requires sacrifice but none shown")
```

---

### 5. ПРОВЕРКА ЛОКАЦИЙ

```python
def validate_locations():
    """Проверяет географию мира"""
    
    # Расстояния
    for location_a, location_b in location_pairs:
        stated_distance = world.distance(location_a, location_b)
        if stated_distance contradicts travel_times:
            warn("Distance inconsistency")
    
    # Уничтоженные локации
    for scene in scenes:
        if scene.location.destroyed_in_chapter < scene.chapter:
            error(f"{scene.location.name} used after destruction")
```

---

## 📊 ОТЧЁТ ВАЛИДАЦИИ

```json
{
  "validation_report": {
    "timestamp": "2025-12-01T23:05:00Z",
    "project": "My Novel",
    "chapters_validated": 24,
    
    "summary": {
      "critical_errors": 2,
      "warnings": 7,
      "suggestions": 15
    },
    
    "critical_errors": [
      {
        "type": "character_death_violation",
        "severity": "critical",
        "location": "ch12, scene 3",
        "description": "Character 'John' speaks but was killed in ch08",
        "fix": "Either revive John or change speaker"
      },
      {
        "type": "timeline_paradox",
        "severity": "critical",
        "location": "ch15",
        "description": "Event happens before its cause (battle before declaration of war)",
        "fix": "Reorder chapters 14 and 15"
      }
    ],
    
    "warnings": [
      {
        "type": "forgotten_subplot",
        "severity": "medium",
        "description": "Romance arc between Anna & Tom not mentioned since ch11 (8 chapters ago)",
        "suggestion": "Add scene or resolve arc"
      }
    ]
  }
}
```

---

**СТАТУС:** ✅ VALIDATION READY
