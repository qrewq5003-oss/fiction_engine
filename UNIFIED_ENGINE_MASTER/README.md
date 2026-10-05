# UNIFIED ENGINE MASTER v2.0

База знаний Fiction Engine для коммерческого и литературного письма.
Собрана из HYBRID ENGINE FULL + UNIFIED ENGINE v3.0 + V1200 META MCL.

---

## КАК ДВИЖОК ИСПОЛЬЗУЕТ БАЗУ

Fiction Engine читает базу сам и вставляет выжимки в промпт каждой главы.
Что именно он читает — перечислено в `INDEX.json` → `runtime_files`
(177 файлов из 249). Справочник для автора — руководства, шаблоны, разборы —
лежит отдельно, в `_reference/`, с той же структурой папок: в промпт он не
попадает. В рабочих папках остались только файлы, которые читает движок, и их
README.

- **Модули `03_ADVANCED_ENGINES/`.** В начале каждого — секции
  `## PROMPT:QUICK` (ядро, идёт во всех режимах) и `## PROMPT:FULL`
  (дополнение для QUALITY и MASTER). Модель получает ровно их. Всё, что ниже,
  — справочник: примеры, схемы, разборы. Хотите изменить то, что получает
  модель, — правьте секции PROMPT; справочник на промпт не влияет.
- **Разделы поджанров** в контрактах `16_GENRE_CONTRACT/` и блоки правил в
  `11_PROMPTS/` помечены якорем — строкой `<!-- genre: detective_classic, … -->`
  (в контракте — под заголовком раздела, в правилах — над строкой-меткой).
  Движок ищет раздел по ключу жанра, модель якорь не получает. Новый поджанр —
  новый якорь; раздел без якоря движок не найдёт. Профили, антагонисты
  `05_CHARACTER_ENGINE/` и арки `12_ARCS/` подбираются по семейству жанра.
  Соответствие коду проверяет `tests/test_unified_contract.py`.
- **Жанровые варианты** в модулях пишутся строкой `**ЖАНР:** …` (ДЕТЕКТИВ,
  НУАР, ТРИЛЛЕР, ХОРРОР, РОМАНТИКА, ФЭНТЕЗИ, НФ, РЕАЛИЗМ, можно через «/»).
  Модель получает вариант только своего жанра.
- **Антиклише** — `00_CORE/anticliche_replacements.md` и `00_CORE/ai_cliches.md`
  — идут в каждый промпт компактно.
- **Жанровые голоса** `13_VOICE_LIBRARY/voice_profiles/` — пресеты на странице
  «Голос»: характер, параметры и принципы, без эталонных отрывков. Голос жанра
  проекта предлагается первым.

После правок базы:

```
cd fiction_engine
python -m pytest tests/test_unified_contract.py tests/test_prompt_snapshots.py tests/test_unified_manifest.py
FE_UPDATE_SNAPSHOTS=1 python -m pytest tests/test_prompt_snapshots.py   # если промпт изменился намеренно
python tests/unified_trace.py                                            # если изменился набор читаемых файлов
```

Описания «автоматических» систем в `_archive/07_SYSTEM_ENGINE/` и в справочных
частях модулей («движок автоматически отслеживает…») — проектные заметки.
То, что из них реализовано, живёт в коде Fiction Engine, а не в этих файлах.

---

## СТРУКТУРА

```
00_CORE/             — ядро: правила, стиль, клише, антиклише
01_WRITING_CORE/     — техники письма: диалоги, описания, эмоции (7 модулей)
03_ADVANCED_ENGINES/ — 25 модулей с секциями PROMPT
04_GENRE_ENGINE/     — 35 жанровых каталогов
05_CHARACTER_ENGINE/ — профили персонажей по жанрам и стилям, антагонисты
06_PATTERN_LIBRARY/  — хуки, переходы, ситуации, паттерны сцен и диалогов
10_VALIDATION/       — чек-листы глав для судьи
11_PROMPTS/          — жанровые промпты по режимам
12_ARCS/             — шаблоны арок
13_VOICE_LIBRARY/    — профили голосов, проверка голоса
14_CHARACTER_DIALECTICS/ — диалектика персонажей
15_SYMBOLISM/        — механика символов
16_GENRE_CONTRACT/   — читательские контракты жанров
17_TONE_LAYERS/      — тона: жуть, экшн, лирика, сатира, романтика, саспенс, нуар, эпика
_reference/          — справочник для автора: не читается движком, те же папки
                       (02_STRUCTURE_ENGINE, 09_TEMPLATES, шаблоны промптов,
                       паттерны диалогов, GENRE_MERGER, antagonist_core…)
_archive/            — устаревшее: не читается движком, см. _archive/README.md
```

---

## РУЧНОЕ ИСПОЛЬЗОВАНИЕ (без Fiction Engine)

Разделы ниже — для работы с базой напрямую, когда файлы вставляются в чат
вручную. Fiction Engine так не работает: он собирает промпт сам, как описано
выше. Упомянутые ниже `CORE_FULL`, `CORE_MINI`, `cliches_list.txt`,
`AUTO_ROUTER.md` и `08_STATE_ENGINE/` лежат в `_archive/` по тем же путям, а
справочные файлы — `02_STRUCTURE_ENGINE/`, `09_TEMPLATES/`, `GENRE_MERGER.md`,
`11_PROMPTS/templates/`, паттерны диалогов и структур глав, `antagonist_core.md`,
`claude_validation_prompt.md` — в `_reference/` по тем же путям.

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

В приложении стиль выбирается на главной странице («Стиль серии»). В промпт
идут суть, характеристики и правило профиля; примеры и «Подходит для» — нет
(примеры модель копирует). Без выбора стиля блок движка его не содержит.

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

v2.0 — 2026: секции PROMPT во всех модулях, манифест runtime_files в INDEX.json.
v1.0 — 2025.
Источники: HYBRID ENGINE FULL, UNIFIED ENGINE v3.0, V1200 META MCL FULL.
Версия ведётся в `INDEX.json` → `version`; тест сверяет её с этим файлом.

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
