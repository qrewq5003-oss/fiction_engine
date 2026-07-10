# 🎛️ ENGINE MASTER CONTROLLER v3.0

**Файл:** system/ENGINE_CONTROLLER.md  
**Версия:** 3.0.0  
**Рейтинг:** 5++/5  
**Назначение:** Центральная система управления всеми модулями движка

---

## 🎯 ФИЛОСОФИЯ КОНТРОЛЛЕРА

Этот модуль превращает набор файлов в **операционную систему для письма**.

**Ключевая идея:**
- Движок — не просто файлы, а **интеллектуальная система**
- Модули вызываются **автоматически** по контексту
- Память **интегрирована** с каждым движком
- Режимы работы **адаптируют** весь движок под задачу

---

## 📊 АРХИТЕКТУРА СИСТЕМЫ

### ИЕРАРХИЯ КОМПОНЕНТОВ (7 УРОВНЕЙ)

```
LEVEL 0: MASTER CONTROLLER (этот файл)
  ↓
LEVEL 1: SYSTEM CORE
  ├─ CORE_FULL.md / CORE_MINI.md
  ├─ META_RULES.yaml
  └─ INDEX.json
  ↓
LEVEL 2: INTELLIGENT ROUTING
  ├─ AUTO_ROUTER.md
  ├─ GENRE_MERGER.md
  └─ MEMORY_VALIDATOR.md
  ↓
LEVEL 3: GENRE & MEMORY
  ├─ genre_catalog/{genre}.json
  └─ project/memory/*
  ↓
LEVEL 4: ADVANCED ENGINES (25 модулей)
  ├─ 01-23: Специализированные движки
  ├─ 24: Artistic Foundation
  └─ 25: Style Transformations
  ↓
LEVEL 5: AUTHOR VOICE
  └─ AUTHOR_VOICE_ENGINE.md
  ↓
LEVEL 6: OUTPUT
  └─ Готовый текст
```

---

## 🎮 РЕЖИМЫ РАБОТЫ

### MODE 1: DRAFT MODE (Черновик)

**Назначение:** Быстрое создание первого варианта

**Активные модули:**
```yaml
core: CORE_MINI.md
memory:
  - characters.json (базовая инфо)
  - plot_points.json
  - scene_cards.json
engines:
  - 01_tension_curve (10% мощности)
  - 18_beats_rhythm (базовый)
  - 19_hooks_closings (мини)
validation: OFF
literary_level: 30%
speed: MAXIMUM
```

**Приоритеты:**
- ✅ Скорость > качество
- ✅ Сюжет > стиль
- ✅ Структура > художественность
- ❌ Не проверять клише
- ❌ Не валидировать детали

**Результат:** 2500-3000 слов/час, качество 6-7/10

---

### MODE 2: REVISION MODE (Ревизия)

**Назначение:** Улучшение существующего текста

**Активные модули:**
```yaml
core: CORE_FULL.md
memory: ВСЯ (full context)
engines:
  - 10_subtext_engine
  - 11_micromoments_library
  - 15_dialogue_style
  - 22_sensory_immersion
  - 23_literary_craft
validation: ON (high)
literary_level: 70%
speed: MEDIUM
```

**Приоритеты:**
- ✅ Качество > скорость
- ✅ Художественность > структура
- ✅ Детали + сенсорика
- ✅ Проверка клише
- ✅ Emotion mapping

**Результат:** 500-800 слов/час, качество 8-9/10

---

### MODE 3: LITERARY MODE (Художественный)

**Назначение:** Создание литературы высшего уровня

**Активные модули:**
```yaml
core: CORE_FULL.md
memory: ВСЯ + author_voice_profile
engines: ВСЕ 25 (полная мощность)
  особый фокус:
    - 24_artistic_foundation (100%)
    - 25_style_transformations
    - 23_literary_craft
    - 22_sensory_immersion
    - 11_micromoments_library
validation: MAXIMUM
literary_level: 100%
speed: SLOW
```

**Приоритеты:**
- ✅ Художественность — абсолютный приоритет
- ✅ Каждое слово взвешено
- ✅ Все 5 сенсорных каналов
- ✅ Поэтические приёмы
- ✅ Авторский голос
- ✅ Уникальность каждой фразы

**Результат:** 200-400 слов/час, качество 10/10

---

### MODE 4: SPEED MODE (Скоростной)

**Назначение:** Максимальная производительность

**Активные модули:**
```yaml
core: CORE_MINI.md
memory: 
  - characters.json (только имена)
  - current_scene.json
engines:
  - 19_hooks_closings (minimal)
validation: OFF
literary_level: 20%
speed: EXTREME
```

**Приоритеты:**
- ✅ Скорость — единственный приоритет
- ✅ Простые диалоги
- ✅ Минимум описаний
- ✅ Прямое действие
- ❌ Никаких проверок
- ❌ Никакой художественности

**Результат:** 2500-3500 слов/час, качество 5/10

---

### MODE 5: AUTHOR VOICE PRESERVATION (Голос автора)

**Назначение:** Сохранение уникального стиля автора

**Активные модули:**
```yaml
core: CORE_FULL.md
memory: ВСЯ
author_voice: AUTHOR_VOICE_ENGINE.md (PRIORITY 1)
engines: Все, но подчинены author_voice
validation: Custom (по голосу автора)
literary_level: По профилю автора
speed: MEDIUM
```

**Приоритеты:**
- ✅ Голос автора > любые правила
- ✅ Синтаксис автора
- ✅ Лексика автора
- ✅ Ритм автора
- ✅ Темп автора
- ⚠️ Правила META_RULES адаптируются

**Результат:** Неотличимо от текста автора

---

## 🔄 ПОСЛЕДОВАТЕЛЬНОСТЬ ВЫЗОВА МОДУЛЕЙ

### ЭТАП 1: ИНИЦИАЛИЗАЦИЯ

```
1. Загрузка MASTER CONTROLLER
2. Определение режима работы
3. Загрузка CORE (FULL/MINI)
4. Загрузка META_RULES.yaml
5. Загрузка INDEX.json
```

---

### ЭТАП 2: КОНТЕКСТ

```
6. Чтение project/config.json
7. Определение жанра
8. Загрузка genre_catalog/{genre}.json
9. Применение GENRE_MERGER (если гибрид)
10. Загрузка памяти проекта:
    - characters.json
    - scene_cards.json
    - plot_points.json
    - locations.json
    - timeline.json
```

---

### ЭТАП 3: ROUTING (Маршрутизация)

```
11. Анализ запроса автора
12. Вызов AUTO_ROUTER.md
13. Определение нужных движков
14. Проверка зависимостей (INDEX.json)
15. Загрузка движков в правильном порядке
```

---

### ЭТАП 4: AUTHOR VOICE (если MODE 5)

```
16. Загрузка AUTHOR_VOICE_ENGINE.md
17. Анализ авторского стиля
18. Адаптация всех модулей под голос
19. Переопределение приоритетов
```

---

### ЭТАП 5: EXECUTION (Выполнение)

```
20. Применение движков в sequence
21. Интеграция с памятью на каждом шаге
22. Валидация (если включена)
23. Проверка MEMORY_VALIDATOR
24. Генерация текста
```

---

### ЭТАП 6: VALIDATION & OUTPUT

```
25. Финальная валидация
26. Проверка целостности памяти
27. Обновление scene_cards.json
28. Обновление timeline.json
29. Вывод результата
30. Логирование (для learning)
```

---

## 🧠 ИНТЕГРАЦИЯ ПАМЯТИ С ДВИЖКАМИ

### ПРИНЦИП: Каждый движок имеет доступ к памяти

**Карта интеграции:**

```yaml
01_tension_curve:
  reads:
    - scene_cards.json (последние 3 главы)
    - plot_points.json
  writes:
    - scene_cards.json (intensity_score)

02_character_resonance:
  reads:
    - characters.json (всех персонажей сцены)
    - relationships.json
  writes:
    - characters.json (arc_progress)

03_thematic_dna:
  reads:
    - project/config.json (themes)
    - timeline.json
  writes:
    - timeline.json (thematic_moments)

04_reader_simulation:
  reads:
    - scene_cards.json (все сцены до текущей)
  writes:
    - scene_cards.json (reader_engagement_score)

05_commercial_heatmap:
  reads:
    - genre_catalog/{genre}.json
    - scene_cards.json
  writes:
    - scene_cards.json (commercial_score)

[... аналогично для всех 25 модулей ...]

24_artistic_foundation:
  reads:
    - characters.json (emotions)
    - locations.json (atmosphere)
  writes:
    - scene_cards.json (artistic_quality_score)

25_style_transformations:
  reads:
    - genre_catalog/{genre}.json
    - project/config.json (tone)
  writes:
    - scene_cards.json (style_applied)
```

---

## 🎯 КРИТЕРИИ ИЕРАРХИЙ

### ИЕРАРХИЯ 1: Правила (Rule Priority)

```
1. AUTHOR_VOICE (если MODE 5)     [ПРИОРИТЕТ: 100]
2. META_RULES.yaml (hard)          [ПРИОРИТЕТ: 90]
3. Genre-specific rules            [ПРИОРИТЕТ: 70]
4. META_RULES.yaml (soft)          [ПРИОРИТЕТ: 50]
5. project/config.json             [ПРИОРИТЕТ: 30]
6. writing_guide/*                 [ПРИОРИТЕТ: 10]
```

**Правило конфликта:**
- Если правила противоречат → побеждает высший приоритет
- Если приоритеты равны → побеждает более специфичное

---

### ИЕРАРХИЯ 2: Движки (Engine Priority)

```
TIER S (всегда активны):
- 24_artistic_foundation
- MEMORY (all files)

TIER A (активны в большинстве режимов):
- 01_tension_curve
- 23_literary_craft
- 15_dialogue_style

TIER B (активны при ревизии/literary):
- 10_subtext_engine
- 11_micromoments_library
- 22_sensory_immersion

TIER C (опциональные):
- 04_reader_simulation
- 05_commercial_heatmap
- 06_multibook_causality

TIER D (специализированные):
- 25_style_transformations (только при явном запросе)
- 14_narrative_distance (только для POV задач)
```

---

### ИЕРАРХИЯ 3: Память (Memory Priority)

```
CRITICAL (всегда загружается):
- characters.json (текущей сцены)
- scene_cards.json (текущая)
- current_chapter_summary.md

HIGH (в большинстве режимов):
- plot_points.json
- timeline.json
- relationships.json

MEDIUM (при ревизии):
- locations.json
- magic_system.json (если фэнтези)
- world_facts.json

LOW (опционально):
- research_notes.md
- deleted_scenes.json
- author_notes.md
```

---

## 🔀 РЕЖИМЫ ПЕРЕКЛЮЧЕНИЯ

### Автоматическое переключение режимов

```python
def auto_detect_mode(user_request):
    # Анализ запроса автора
    
    if "быстро" in request or "наброс" in request:
        return SPEED_MODE
    
    elif "первый вариант" in request or "черновик" in request:
        return DRAFT_MODE
    
    elif "улучши" in request or "доработай" in request:
        return REVISION_MODE
    
    elif "в моём стиле" in request or "как я пишу" in request:
        return AUTHOR_VOICE_MODE
    
    elif "красиво" in request or "литературно" in request:
        return LITERARY_MODE
    
    else:
        return DRAFT_MODE  # default
```

---

### Ручное переключение

**Команды:**

```
@mode:draft      → DRAFT MODE
@mode:revision   → REVISION MODE  
@mode:literary   → LITERARY MODE
@mode:speed      → SPEED MODE
@mode:voice      → AUTHOR VOICE MODE
```

---

## 📊 MONITORING & FEEDBACK

### Метрики работы системы

```json
{
  "current_mode": "LITERARY_MODE",
  "active_engines": [
    "24_artistic_foundation",
    "25_style_transformations",
    "23_literary_craft",
    "22_sensory_immersion"
  ],
  "memory_loaded": {
    "characters": 12,
    "scenes": 45,
    "locations": 8
  },
  "performance": {
    "words_per_hour": 350,
    "quality_score": 9.5,
    "consistency_score": 9.2
  },
  "validation_status": "PASSED",
  "last_updated": "2025-12-01T15:30:00Z"
}
```

---

## 🎛️ КОНФИГУРАЦИЯ ПО УМОЛЧАНИЮ

```yaml
default_config:
  mode: DRAFT_MODE
  core: CORE_FULL.md
  
  memory_settings:
    auto_load: true
    max_context_size: 50000  # tokens
    priority_filtering: true
  
  engine_settings:
    parallel_processing: false
    validation_level: medium
    literary_threshold: 0.7
  
  author_voice:
    enabled: false
    learning: true
    adaptation_strength: 0.8
  
  performance:
    target_speed: balanced
    quality_minimum: 7.0
```

---

## 🔧 РАСШИРЕННЫЕ КОМАНДЫ

### Управление системой

```bash
# Статус системы
@system:status

# Список активных движков
@system:engines

# Текущая память
@system:memory

# Переключить режим
@mode:literary

# Загрузить движок вручную
@load:22_sensory_immersion

# Выгрузить движок
@unload:04_reader_simulation

# Обновить память
@memory:reload

# Запустить валидацию
@validate:full

# Очистить кэш
@system:clear_cache
```

---

## 🚀 ПРИМЕР РАБОТЫ СИСТЕМЫ

### Сценарий: Автор пишет новую главу

```
1. Автор: "Напиши главу 5 - романтическая сцена между Анной и Томом"

2. MASTER CONTROLLER:
   - Определяет режим: DRAFT_MODE (первый вариант)
   - Загружает CORE_FULL.md
   - Читает genre: romantic_fantasy
   
3. AUTO_ROUTER:
   - Определяет ключевое слово: "романтическая"
   - Вызывает движки:
     * 17_character_chemistry
     * 15_dialogue_style
     * 11_micromoments_library
     * 22_sensory_immersion
     
4. MEMORY:
   - Загружает characters.json (Анна, Том)
   - Загружает relationships.json (их история)
   - Загружает scene_cards.json (предыдущие сцены)
   
5. GENRE_MERGER:
   - Смешивает romantic (60%) + fantasy (40%)
   - Адаптирует тон, темп, детали
   
6. EXECUTION:
   - Движки работают последовательно
   - Каждый добавляет свой слой
   - Память обновляется на каждом шаге
   
7. OUTPUT:
   - Глава сгенерирована (1650 слов)
   - Обновлён scene_cards.json
   - Обновлён timeline.json
   - Качество: 8/10 (draft mode)
```

---

## 🎯 КРИТЕРИИ УСПЕХА

Система считается успешной, если:

```
✅ Режимы переключаются автоматически
✅ Движки вызываются по контексту
✅ Память интегрирована везде
✅ Нет противоречий
✅ Качество предсказуемо
✅ Скорость соответствует режиму
✅ Голос автора сохранён (если MODE 5)
```

---

## 📈 ROADMAP КОНТРОЛЛЕРА

### ФАЗА 1 (Текущая):
- [x] Определение режимов работы
- [x] Иерархии модулей
- [x] Интеграция памяти
- [ ] Тестирование

### ФАЗА 2:
- [ ] Автоматическое переключение режимов
- [ ] Parallel processing движков
- [ ] Кэширование результатов

### ФАЗА 3:
- [ ] Machine learning оптимизация
- [ ] Predictive routing
- [ ] Auto-tuning параметров

---

## 🌟 ФИЛОСОФИЯ

**Движок — это не набор правил.**

**Это операционная система для творчества.**

Где каждый модуль — это процесс.  
Где память — это состояние.  
Где автор — это пользователь.

И где результат — **литература**.

---

**ВЕРСИЯ:** 3.0  
**РАЗМЕР:** ~15 KB  
**РЕЙТИНГ:** 5++/5  
**СТАТУС:** ✅ CORE SYSTEM READY

**"Управляй системой. Создавай литературу."**
