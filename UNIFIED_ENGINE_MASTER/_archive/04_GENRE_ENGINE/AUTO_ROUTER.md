# AUTO-ROUTER ENGINE

**Файл:** `engine/auto_router.py`  
**Версия:** реальная (соответствует коду)

---

## КАК РАБОТАЕТ

Двухуровневый роутер — сначала keyword matching без LLM, потом LLM если нужно.

```
Задача писателя
      ↓
route_by_keywords(task_text, genre_key)
      ↓
confidence >= 2?
  ДА → вернуть результат (быстро, бесплатно)
  НЕТ → resolve_modules_dynamic() через LLM (точнее для нестандартных задач)
      ↓
BASE_MODULES + выбранные модули
```

`BASE_MODULES` добавляются всегда:
- `07_voice_consistency`
- `19_hooks_closings`
- `10_subtext_engine`

---

## ТАБЛИЦА КЛЮЧЕВЫХ СЛОВ (основные)

| Ключевые слова | Модули |
|---|---|
| красиво, поэтично, литературно, образно | `24_artistic_foundation`, `23_literary_craft` |
| атмосфера, запах, звук, сенсорика | `22_sensory_immersion` |
| нуар, минимализм, барокко, лирика | `25_style_transformations` |
| диалог, реплики, разговор | `15_dialogue_style`, `10_subtext_engine` |
| напряжение, саспенс, конфликт | `01_tension_curve`, `20_stakes_escalation` |
| темп, ритм, динамика, экшен | `12_pacing_engine`, `18_beats_rhythm` |
| медленно, деталь, замедлить | `11_micromoments_library` |
| психология, внутренний, мотивация | `09_deep_character_psychology`, `16_pov_filters` |
| химия, отношения, притяжение | `17_character_chemistry`, `02_character_resonance` |
| тема, смысл, идея | `03_thematic_dna` |
| серия, арка, долгосрочно | `06_multibook_causality` |
| голос, стиль автора | `07_voice_consistency`, `21_voice_constructor` |

Полная таблица: `KEYWORD_ROUTES` в `engine/auto_router.py` (~80 ключей).

---

## ЖАНРОВЫЕ УСИЛИТЕЛИ

При определённом жанре часть модулей получает дополнительный приоритет:

| Жанр | Усилители |
|---|---|
| detective | `13_foreshadowing_engine`, `10_subtext_engine`, `04_reader_simulation` |
| horror | `01_tension_curve`, `22_sensory_immersion`, `25_style_transformations` |
| romance | `17_character_chemistry`, `11_micromoments_library`, `02_character_resonance` |
| thriller | `01_tension_curve`, `20_stakes_escalation`, `04_reader_simulation` |
| fantasy | `22_sensory_immersion`, `08_world_state_kernel` |
| realism | `11_micromoments_library`, `09_deep_character_psychology`, `14_narrative_distance` |

---

## КАК ИСПОЛЬЗОВАТЬ В КОДЕ

```python
from engine.auto_router import auto_route, explain_routing

# Роутинг по задаче
modules = auto_route(
    task_text="Напряжённая сцена допроса с подтекстом",
    genre_key="detective_noir",
)
# → ["07_voice_consistency", "19_hooks_closings", "10_subtext_engine",
#    "15_dialogue_style", "01_tension_curve", "13_foreshadowing_engine"]

# Объяснение (отладка)
print(explain_routing(task_text, genre_key))
```

Роутер вызывается автоматически в `unified_engine.py → _select_modules()`
при `mode="master"` если `pre_selected_modules=None`.

---

## ОТЛАДКА

Если модули выбираются неправильно:
1. `explain_routing(task_text, genre_key)` — покажет какие ключи совпали
2. Добавить ключевое слово в `KEYWORD_ROUTES` в `auto_router.py`
3. Или передать `pre_selected_modules=[...]` напрямую в `build_engine_context()`
