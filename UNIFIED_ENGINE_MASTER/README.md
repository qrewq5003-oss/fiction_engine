# UNIFIED ENGINE MASTER v1.0

Объединённый движок для коммерческого и литературного письма.
Собран из HYBRID ENGINE FULL + UNIFIED ENGINE v3.0 + V1200 META MCL.

---

## СТРУКТУРА

```
00_CORE/          — Ядро: правила, стиль, клише
01_WRITING_CORE/  — Техники письма: диалоги, описания, эмоции (7 модулей)
02_STRUCTURE_ENGINE/ — Структура: шаблоны сцен, tension_model, arc_validator
03_ADVANCED_ENGINES/ — 25 специализированных движков
04_GENRE_ENGINE/  — 26 жанров + GENRE_MERGER + AUTO_ROUTER
05_CHARACTER_ENGINE/ — Профили персонажей по жанрам и стилям
06_PATTERN_LIBRARY/  — Паттерны сцен и диалогов с примерами
07_SYSTEM_ENGINE/ — Системные модули: голос автора, контроллер
08_STATE_ENGINE/  — Управление состоянием для длинных серий
09_TEMPLATES/     — JSON шаблоны проекта
```

---

## РЕЖИМЫ РАБОТЫ

### QUICK — коммерческая генерация
Загружай в контекст:
- `00_CORE/CORE_MINI.md`
- `00_CORE/META_RULES.yaml`
- `00_CORE/cliches_list.txt`
- `04_GENRE_ENGINE/catalog/{твой_жанр}.json`
- `02_STRUCTURE_ENGINE/scene_template.md`

Размер контекста: ~25KB. Максимальная скорость.

### QUALITY — литературное письмо
Загружай в контекст:
- `00_CORE/CORE_FULL.md`
- `00_CORE/META_RULES.yaml`
- `01_WRITING_CORE/` (нужные модули)
- `04_GENRE_ENGINE/catalog/{твой_жанр}.json`
- `05_CHARACTER_ENGINE/profiles/GENRE/{жанр}.md`
- `05_CHARACTER_ENGINE/profiles/STYLE/{стиль}.md`
- Нужные модули из `03_ADVANCED_ENGINES/`

Размер контекста: ~80KB. Высокое качество.

### MASTER — длинные серии (100+ глав)
Всё из QUALITY плюс:
- `08_STATE_ENGINE/global_state.md`
- `08_STATE_ENGINE/plot_matrix.md`
- `08_STATE_ENGINE/memory_graph.md`
- Текущее состояние проекта

Размер контекста: ~120KB. Максимальный контроль.

---

## КАК ВЫБРАТЬ ЖАНР

Доступные жанры в `04_GENRE_ENGINE/catalog/`:

**Детектив:** detective_action, detective_classic, detective_cozy, detective_noir, detective_procedural, detective_psychological  
**Фэнтези:** fantasy_dark, fantasy_epic, fantasy_romantic, fantasy_sword_sorcery, fantasy_urban  
**Хоррор:** horror_cosmic, horror_gothic, horror_survival  
**Романтика:** romance_contemporary, romance_historical, romance_paranormal  
**НФ:** scifi_cyberpunk, scifi_hard, scifi_post_apocalyptic, scifi_social, scifi_space_opera, scifi_steampunk  
**Реализм:** realism_family_saga, realism_psychological, realism_social

Для смешивания жанров: `04_GENRE_ENGINE/GENRE_MERGER.md`  
Для автоматического выбора модулей: `04_GENRE_ENGINE/AUTO_ROUTER.md`

---

## КАК ВЫБРАТЬ СТИЛЬ

Стилевые профили в `05_CHARACTER_ENGINE/profiles/STYLE/`:

- `cinematic` — визуальный, монтажный, без лишнего
- `commercial` — максимальная читаемость, высокий темп
- `literary` — язык как ценность, плотный смысл
- `atmospheric` — место и атмосфера как персонаж
- `dialogue_focused` — история через диалог
- `emotional_depth` — внутренний мир главное
- `epic_voice` — масштаб и историческая важность
- `first_person_close` — читатель внутри головы
- `modern_minimal` — меньше слов, больше пространства
- `noir_style` — цинизм, усталость, чёрный юмор
- `omniscient` — нарратор знает всё
- `tight_thriller` — напряжение через экономию слов

---

## КАК ИСПОЛЬЗОВАТЬ AUTO_ROUTER

Открой `04_GENRE_ENGINE/AUTO_ROUTER.md`.  
Найди свой запрос в таблице маршрутизации.  
Загрузи указанные модули из `03_ADVANCED_ENGINES/` в контекст.

Пример: "хочу добавить напряжение" → загружай `01_tension_curve.md`, `20_stakes_escalation.md`, `13_foreshadowing_engine.md`

---

## КАК ИСПОЛЬЗОВАТЬ STATE ENGINE

После каждой финальной главы обновляй:
- `global_state.md` — что изменилось у персонажей и в мире
- `plot_matrix.md` — статус сюжетных линий
- `memory_graph.md` — что теперь знают персонажи

Подавай актуальное состояние в контекст при генерации следующей главы.

---

## ПАТТЕРНЫ

`06_PATTERN_LIBRARY/scenes/`:
- `atmospheric_scene.md` — атмосферная сцена
- `dynamic_scene.md` — экшн и динамика
- `emotional_scene.md` — эмоциональная сцена
- `chapter_structures.md` — три структуры глав

`06_PATTERN_LIBRARY/dialogues/`:
- `cinematic_dialogue.md` — диалог с напряжением
- `minimalistic_dialogue.md` — диалог через паузы
- `subtext_dialogue.md` — два уровня разговора

---

## ВЕРСИЯ

v1.0 — 2025  
Источники: HYBRID ENGINE FULL, UNIFIED ENGINE v3.0, V1200 META MCL FULL

---

## НОВЫЕ МОДУЛИ (v1.1)

### 05_CHARACTER_ENGINE/antagonists/
- `antagonist_core.md` — ядро: функции, типы по мотивации, обязательные характеристики
- `antagonist_by_genre.md` — антагонист в каждом жанре: детектив, триллер, романтика, фэнтези, хоррор, НФ, психологический, городская мистика

### 06_PATTERN_LIBRARY/genre_situations/
- `detective_situations.md` — допрос, осмотр места, ложный подозреваемый, раскрытие
- `romance_situations.md` — первая встреча, вынужденная близость, чёрный момент, HEA
- `thriller_situations.md` — преследование, предательство, дедлайн, ложный союзник
- `fantasy_situations.md` — магическая битва, раскрытие тайны мира, моральный выбор, уход наставника
- `horror_situations.md` — первое столкновение, изоляция, недоверие к восприятию
- `scifi_situations.md` — введение допущения, этическая дилемма, контакт с иным
- `universal_situations.md` — смерть второстепенного, предательство, герой в слабости, раскрытие тайны, финальная конфронтация

### 06_PATTERN_LIBRARY/transitions/
- `scene_transitions.md` — 6 типов переходов: монтажный, временной, смена POV, клиффхэнгер, тихий финал, параллельный монтаж

### 10_VALIDATION/
- `checklist_universal.md` — универсальный чеклист для любой главы
- `checklist_detective.md` — детектив
- `checklist_romance.md` — романтика
- `checklist_thriller.md` — триллер
- `checklist_fantasy.md` — фэнтези
- `checklist_horror.md` — хоррор
- `claude_validation_prompt.md` — готовый промпт для валидации через Claude с JSON форматом ответа
