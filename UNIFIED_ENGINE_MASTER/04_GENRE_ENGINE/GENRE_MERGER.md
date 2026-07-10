# GENRE MERGER

**Версия:** реальная (соответствует коду)

---

## КАК РАБОТАЕТ В РЕАЛЬНОСТИ

Нет отдельного "движка смешивания". Жанр определяется как один через `detect_genre()`,
потом загружается каталог этого жанра + его специфические модули.

Для гибридов (например, детектив + романтика) система работает так:

```python
# 1. detect_genre() выбирает наиболее специфичное совпадение по ключевым словам
genre_key = detect_genre("романтический детектив")  # → "detective_classic" или "romance_contemporary"

# 2. Если нужен настоящий гибрид — используй GENRE_MODULES напрямую
from engine.unified_engine import build_engine_context

context = build_engine_context(
    genre_text="detective noir",
    mode="quality",
    pre_selected_modules=[
        "17_character_chemistry",   # романтика
        "01_tension_curve",         # детектив
        "10_subtext_engine",        # общее
        "15_dialogue_style",
    ]
)
```

---

## ПОПУЛЯРНЫЕ ГИБРИДЫ

Рекомендуемые комбинации модулей для частых жанровых смесей:

**Детектив + Романтика**
```
genre_text: "detective_noir"
extra_modules: [17_character_chemistry, 02_character_resonance, 11_micromoments_library]
```

**Фэнтези + Хоррор (тёмное фэнтези)**
→ Используй `fantasy_dark` — он уже содержит horror-элементы в каталоге.

**Фэнтези + Детектив (городское фэнтези)**
```
genre_text: "fantasy_urban"
extra_modules: [13_foreshadowing_engine, 10_subtext_engine, 04_reader_simulation]
```

**НФ + Триллер**
```
genre_text: "scifi_cyberpunk"
extra_modules: [01_tension_curve, 20_stakes_escalation, 14_narrative_distance]
```

**Реализм + Психологический триллер**
```
genre_text: "realism_psychological"
extra_modules: [01_tension_curve, 09_deep_character_psychology, 16_pov_filters]
```

---

## ТЕХНИЧЕСКИ

Жанровые каталоги в `04_GENRE_ENGINE/catalog/` содержат `subgenre_notes` поле
с указанием с какими жанрами данный жанр хорошо гибридизируется.

Пример из `detective_noir.json`:
```
"subgenre_notes": "Может гибридизироваться с фэнтези (городское фэнтези + нуар),
НФ (киберпанк-нуар), хоррором (нуар + ужас)"
```

Передача `pre_selected_modules` в `build_engine_context()` позволяет собрать
любой гибрид — роутер тогда пропускается, используются именно эти модули.
