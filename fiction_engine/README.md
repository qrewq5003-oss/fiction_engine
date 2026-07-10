# Fiction Engine — Полное приложение

## Что умеет

**Два интерфейса:**
- Браузер (`localhost:5000`) — для удобной работы с текстом и State Engine
- Терминал (`python3 cli.py`) — для быстрых действий без мыши

**Несколько API:**
- Anthropic (прямой) — Claude для анализа глав
- nano-gpt.com — доступ к 300+ моделям: GPT-5, Gemini 2.5 Pro, DeepSeek, Claude, специализированные модели для прозы

**Что автоматизирует:**
1. Анализ главы → показывает изменения → ты подтверждаешь → State Engine обновляется
2. Сборка промпта — автоматически берёт контекст из State Engine + голос из последних глав
3. История — все главы и обновления хранятся в локальной БД

---

## Установка

```bash
# Распакуй архив
unzip fiction_engine_app.zip
cd fiction_engine_app

# Установка зависимостей
bash setup.sh
```

---

## Запуск

```bash
# Оба интерфейса сразу (рекомендуется):
bash run.sh

# Только браузер:
python3 web/app.py
# Открой: http://localhost:5000

# Только терминал:
python3 cli.py

# Терминал с командой напрямую:
python3 cli.py status
python3 cli.py analyze
python3 cli.py prompt
python3 cli.py chapter
```

---

## Первый запуск

1. **Добавь API ключи** — браузер: `/settings` или терминал: `python3 cli.py keys`

2. **Создай проект** — укажи название и жанр серии

3. **Загрузи главы** — через браузер (перетащи файл) или терминал

4. **Заполни State Engine** — браузер: `/state` — персонажи, линии, кто что знает

---

## Рабочий процесс

### После каждой написанной главы:
1. Загрузи .txt файл через браузер или `python3 cli.py chapter`
2. Нажми «Анализ» → выбери модель → подтверди изменения
3. Проверь и отредактируй State Engine если нужно

### Перед написанием следующей:
1. `python3 cli.py prompt` или браузер `/prompt`
2. Выбери режим (QUICK / QUALITY / MASTER)
3. Скопируй готовый промпт → заполни `[поля в скобках]` → подай в GPT

---

## Выбор модели

Рекомендации для разных задач:

| Задача | Модель |
|--------|--------|
| Анализ глав | claude-opus-4.6 (прямой) |
| Генерация QUICK | openai/gpt-5.2 или claude-sonnet-4 |
| Генерация QUALITY | claude-opus-4 или gemini-2.5-pro |
| Специализированная проза | Sao10K/L3.3-70B-Euryale-v2.3 |
| Экономия токенов | gemini-2.5-flash или gpt-5-mini |

---

## Структура файлов

```
fiction_engine_app/
├── cli.py              — терминальный интерфейс
├── run.sh              — запуск всего
├── setup.sh            — установка
├── engine/
│   ├── api.py          — клиенты API (Anthropic + nano-gpt)
│   ├── db.py           — SQLite база данных
│   └── state.py        — State Engine логика + генерация промптов
└── web/
    ├── app.py          — Flask веб-сервер
    └── templates/      — HTML шаблоны

~/fiction_engine/       — данные (создаётся автоматически)
├── projects.db         — все проекты, главы, State Engine
└── prompts_out/        — сохранённые промпты
```

---

## Зависимости

- Python 3.10+
- `anthropic` — прямой API
- `openai` — для nano-gpt (OpenAI-совместимый)
- `flask` — веб-интерфейс

---

## v4.0 — Архитектурный рефакторинг

### Изменения

**db.py разделён на три слоя** (обратная совместимость сохранена — все `from .db import ...` работают без изменений):
- `db_core.py` — соединение, схема, миграции, логирование ошибок
- `db_settings.py` — API ключи, настройки, prep-секции
- `db_projects.py` — проекты, главы, state, pipeline, память, символы, KB
- `db.py` — тонкий re-экспортёр, трогать не нужно

**Silent failures → log_error()**

Все `except Exception: pass` заменены на запись в таблицу `engine_error_log`.
Смотреть ошибки: `from engine.db import get_error_log; get_error_log()`.

**Pipeline — конфигурируемые шаги**

```python
from engine.pipeline import PipelineStep, start_pipeline

# Стандартный запуск
start_pipeline(project_id, chapter_num, prompt, ...)

# Без судьи (быстрый черновик)
fast_steps = [PipelineStep("generate"), PipelineStep("critique")]
start_pipeline(..., steps=fast_steps)

# Только критика существующего текста
critique_only = [PipelineStep("critique")]
start_pipeline(..., steps=critique_only)
```

**L3 Memory ↔ Prevalidation**

`prevalidate_chapter()` теперь автоматически получает активные сюжетные обещания
из предыдущих саммари и проверяет: не нарушает ли задача главы promises.
Новая функция: `get_l3_active_promises(project_id, before_chapter, n)`.

**unified_engine — явный decision point**

`_select_modules()` — единственное место где выбирается стратегия модулей
(keyword routing / LLM resolver / статический набор).
`build_engine_context()` теперь чистый builder без внутренних стратегических решений.

---

## v4.2 — Cognitive Layer

### Новые модули

**`engine/cognitive_memory.py`** — умная замена `get_l3_context()`.

Каждое поле саммари получает вес и скорость затухания:
- `promises` — вес 5, decay 0.0 (никогда не гаснет)
- `conflicts` — вес 4, decay 0.05
- `characters` — вес 3, decay 0.08
- `events` — вес 2, decay 0.12
- `mood` — вес 1, decay 0.20

При выборке последние 2 главы включаются всегда, `promises` из всех глав, остальное — по убыванию effective_score.

**`engine/chapter_analyzer.py`** — структурный анализ главы после написания.

LLM заполняет `ChapterAnalysis`:
```python
analysis.arc_progress        # {'Марина': 'продвинулась: узнала о предательстве'}
analysis.logical_gaps        # ['Марина знала номер — но ей его не называли']
analysis.opened_promises     # ['Записная книжка — что в ней?']
analysis.causal_chains       # [CausalChain(cause, effect, is_setup)]
analysis.conflict_score      # 0.75
analysis.pacing_note         # 'нарастающий'
```

Результат блока `format_analysis_for_prompt(analysis)` автоматически добавляется в контекст следующей генерации.

**`engine/error_policy.py`** — централизованная политика ошибок.

```python
from engine.error_policy import error_boundary, ErrorLevel

@error_boundary(level=ErrorLevel.DEGRADED, fallback="")
def load_voice_context(project_id): ...

# Три уровня:
# RECOVERABLE — тихий fallback, пользователь не видит
# DEGRADED    — предупреждение, функция деградирует
# FATAL       — бросает PipelineError, пользователь должен узнать
```

### TypedDict контракты (`engine/contracts.py`)

`SummaryDict`, `EngineContextDict`, `ChapterAnalysisDict`, `PipelineResultDict` — явные типы для всех структур данных.

### Изменения в существующем коде

- `pipeline.py` — все `log_error()` заменены на `handle_error()` с уровнями; после генерации автоматически запускается `analyze_chapter_deep()`
- `prevalidation.py` — использует `get_weighted_promises()` вместо `get_l3_active_promises()`; promises из всех глав (n=10 вместо 5)
- `narrative_intelligence.py` — синглтон `get_nil()` теперь получает данные через cognitive layer
- `db_core.py` + `db_projects.py` — новая таблица `chapter_analysis`
