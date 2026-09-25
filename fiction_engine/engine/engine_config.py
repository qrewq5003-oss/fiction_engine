"""
engine_config.py — конфигурация UNIFIED ENGINE.

Только данные: словари, списки, скомпилированные паттерны.
Никакой логики, никаких импортов кроме re.
Менять жанровые маппинги, веса и модули — здесь.
"""

import re

# ─── Жанровый маппинг ─────────────────────────────────────────────────────────

GENRE_KEYWORDS = {
    # ─── Фэнтези ──────────────────────────────────────────────────────────────
    "fantasy_dark":            ["тёмное фэнтези", "темное фэнтези", "dark fantasy",
                                "мрачное фэнтези", "тёмная фантастика", "grimdark",
                                "гримдарк", "мрачная магия", "тёмная магия",
                                "кровь и магия", "жестокое фэнтези"],
    "fantasy_epic":            ["эпическое фэнтези", "epic fantasy",
                                "фэнтези", "фэнтэзи", "fantasy",
                                "фентези", "фентэзи",
                                "магия", "волшебство", "магический мир",
                                "высокое фэнтези", "high fantasy",
                                "эльфы", "гномы", "орки", "драконы",
                                "средневековье магия", "средневековый мир",
                                "магические существа", "магический народ",
                                "янг эдалт фэнтези", "young adult fantasy"],
    "fantasy_urban":           ["городское фэнтези", "urban fantasy",
                                "городская магия", "магический реализм",
                                "современная магия", "магия в городе",
                                "городская мистика", "городской"],
    "fantasy_romantic":        ["романтическое фэнтези", "любовное фэнтези",
                                "фэнтези роман", "магическая любовь"],
    "fantasy_sword_sorcery":   ["меч и магия", "sword sorcery",
                                "героическое фэнтези", "боевое фэнтези",
                                "приключенческое фэнтези", "приключения",
                                "рыцари магия", "рыцарский роман",
                                "средневековье", "рыцари", "варвар"],
    # ─── Детектив ─────────────────────────────────────────────────────────────
    "detective_noir":          ["детектив нуар", "нуар детектив", "noir detective",
                                "нуар", "noir", "криминальный нуар",
                                "hard-boiled", "хардбойлд", "частный сыщик нуар",
                                "гангстеры", "мафия", "криминал", "преступный мир",
                                "организованная преступность", "гангстерский"],
    "detective_classic":       ["классический детектив", "детектив",
                                "детективы", "расследование", "murder mystery",
                                "криминальный роман", "crime fiction",
                                "частный сыщик", "следствие",
                                "детектив с разгадкой", "комнатный детектив",
                                "agatha christie", "агата кристи",
                                "детективная история", "детективная проза",
                                "кто убийца", "whodunit"],
    "detective_psychological": ["психологический детектив",
                                "детектив с психологией"],
    "detective_procedural":    ["процедурный детектив", "полицейская процедура",
                                "полицейский детектив", "следователь",
                                "криминальная процедура", "police procedural",
                                "полиция", "следак", "опер"],
    "detective_action":        ["боевой детектив", "экшн детектив",
                                "детектив боевик"],
    "detective_cozy":          ["уютный детектив", "cozy mystery", "cozy",
                                "мягкий детектив", "бытовой детектив"],
    # ─── Триллер ──────────────────────────────────────────────────────────────
    "thriller_psychological":  ["психологический триллер", "thriller", "триллер",
                                "напряжённый триллер", "suspense",
                                "саспенс", "психологическое напряжение",
                                "mind games", "манипуляция",
                                "психологическое давление", "игра разума"],
    "thriller_spy":            ["шпионский триллер", "spy thriller",
                                "шпионаж", "шпион", "разведчик",
                                "секретный агент", "spy fiction", "espionage",
                                "разведка", "контрразведка", "агент под прикрытием"],
    "thriller_survival":       ["триллер выживания", "survival thriller",
                                "выживание", "survival", "борьба за жизнь"],
    # ─── Хоррор ───────────────────────────────────────────────────────────────
    "horror_psychological":    ["психологический хоррор", "psychological horror",
                                "хоррор", "horror", "ужасы", "ужас",
                                "страх", "пугающий", "жуткий", "страшный",
                                "мистика", "мистический", "мистический роман",
                                "страшный рассказ", "страшное",
                                "сверхъестественное", "паранормальное",
                                "призраки", "демоны", "haunting",
                                "потустороннее", "духи", "нечисть"],
    "horror_cosmic":           ["космический хоррор", "лавкрафт", "lovecraft",
                                "cosmic horror", "лавкрафтовский",
                                "неизведанный ужас", "existential horror",
                                "древние боги", "old ones"],
    "horror_gothic":           ["готический хоррор", "gothic horror", "готика",
                                "готический роман", "gothic fiction",
                                "gothic", "gothic romance", "тёмная атмосфера",
                                "вампиры", "оборотни", "вурдалак",
                                "замок с тайнами", "готический особняк"],
    "horror_survival":         ["хоррор выживания", "survival horror",
                                "хоррор выживальщик", "зомби", "зомби апокалипсис",
                                "zombie", "монстры нападают"],
    # ─── Sci-Fi ───────────────────────────────────────────────────────────────
    "scifi_cyberpunk":         ["киберпанк", "cyberpunk", "хакеры будущее",
                                "корпорации будущего", "hi-tech low-life",
                                "нейроинтерфейс", "виртуальная реальность вр",
                                "корпоративная антиутопия"],
    "scifi_hard":              ["твёрдая нф", "твердая нф", "научная фантастика",
                                "hard sci-fi", "hard scifi",
                                "нф", "sci-fi", "sci fi", "scifi", "sf",
                                "фантастика", "фантастический",
                                "научная", "космос наука",
                                "будущее", "будущее технологии",
                                "роботы", "искусственный интеллект нф",
                                "космос", "звёзды", "межзвёздный",
                                "инопланетяне", "пришельцы", "aliens"],
    "scifi_space_opera":       ["космическая опера", "space opera",
                                "космос приключения", "галактическая империя",
                                "межгалактический", "планетарная фантастика"],
    "scifi_post_apocalyptic":  ["постапок", "постапокалипсис", "post-apocalyptic",
                                "после катастрофы", "конец света",
                                "апокалипсис", "постапокалиптический",
                                "dystopia", "дистопия", "антиутопия",
                                "мир после войны", "радиация выживание"],
    "scifi_steampunk":         ["стимпанк", "steampunk", "пар технологии",
                                "викторианская фантастика", "паровые машины"],
    "scifi_social":            ["социальная нф", "social sci-fi", "social scifi",
                                "социальная фантастика", "утопия",
                                "общество будущего", "социальная антиутопия"],
    # ─── Романтика ────────────────────────────────────────────────────────────
    "romance_contemporary":    ["современный роман", "современная романтика",
                                "романтика", "романтический", "романс", "romance",
                                "любовный роман", "любовная история",
                                "любовь", "любовная проза",
                                "любовь современность", "contemporary romance",
                                "любовная линия", "лавстори", "love story",
                                "отношения история", "чувства история"],
    "romance_historical":      ["исторический роман", "историческая романтика",
                                "любовь в прошлом", "historical romance",
                                "регентский роман", "regency romance",
                                "исторический", "история любовь",
                                "викторианская любовь", "средневековая любовь"],
    "romance_paranormal":      ["паранормальный роман", "паранормальная романтика",
                                "любовь вампиры", "любовь оборотни",
                                "paranormal romance", "вампир любовь",
                                "оборотень любовь", "магия любовь"],
    # ─── Реализм ──────────────────────────────────────────────────────────────
    "realism_psychological":   ["психологическая проза", "психологический реализм",
                                "реализм", "реалистичный", "реалистическая проза",
                                "литература", "литературный", "проза",
                                "художественная литература", "literary fiction",
                                "современная проза", "серьёзная литература",
                                "бытовой реализм", "внутренний монолог",
                                "поток сознания", "драма", "бытовая драма",
                                "жизненная история", "жизненный реализм",
                                "молодёжная проза", "young adult"],
    "realism_social":          ["социальная проза", "социальный реализм",
                                "общественная драма", "социальная драма",
                                "война литература", "военная проза",
                                "исторический реализм", "историческая проза"],
    "realism_family_saga":     ["семейная сага", "семейный роман",
                                "несколько поколений", "dynasty", "dynastic",
                                "семейная история", "история семьи",
                                "поколения семья"],
}

# ─── Граф зависимостей модулей ────────────────────────────────────────────────

MODULE_DEPENDENCIES = {
    "11_micromoments_library":    ["24_artistic_foundation"],
    "17_character_chemistry":     ["02_character_resonance"],
    "13_foreshadowing_engine":    ["03_thematic_dna"],
    "10_subtext_engine":          ["15_dialogue_style"],
    "20_stakes_escalation":       ["01_tension_curve"],
    "09_deep_character_psychology": ["02_character_resonance"],
    "25_style_transformations":   ["24_artistic_foundation", "23_literary_craft"],
    "22_sensory_immersion":       ["24_artistic_foundation"],
    "16_pov_filters":             ["14_narrative_distance"],
    "18_beats_rhythm":            ["12_pacing_engine"],
    "05_commercial_heatmap":      ["04_reader_simulation", "12_pacing_engine"],
    "06_multibook_causality":     ["03_thematic_dna"],
}

# ─── Модули по режиму ─────────────────────────────────────────────────────────

MODE_MODULES = {
    "quick": [
        "19_hooks_closings",
        "12_pacing_engine",
        "07_voice_consistency",
    ],
    "quality": [
        "19_hooks_closings",
        "12_pacing_engine",
        "10_subtext_engine",
        "17_character_chemistry",
        "01_tension_curve",
        "07_voice_consistency",
    ],
    "master": [
        "19_hooks_closings",
        "01_tension_curve",
        "20_stakes_escalation",
        "10_subtext_engine",
        "13_foreshadowing_engine",
        "09_deep_character_psychology",
        "22_sensory_immersion",
        "17_character_chemistry",
        "07_voice_consistency",
    ],
}

# Жанровые добавки к базовым наборам модулей
GENRE_MODULES = {
    "fantasy_dark":            ["22_sensory_immersion", "20_stakes_escalation"],
    "fantasy_epic":            ["20_stakes_escalation", "13_foreshadowing_engine", "06_multibook_causality"],
    "fantasy_urban":           ["17_character_chemistry", "10_subtext_engine"],
    "fantasy_sword_sorcery":   ["01_tension_curve", "18_beats_rhythm"],
    "thriller_psychological":  ["01_tension_curve", "20_stakes_escalation", "09_deep_character_psychology", "16_pov_filters"],
    "thriller_spy":            ["10_subtext_engine", "16_pov_filters", "15_dialogue_style", "04_reader_simulation"],
    "thriller_survival":       ["20_stakes_escalation", "01_tension_curve", "12_pacing_engine", "22_sensory_immersion"],
    "detective_classic":       ["13_foreshadowing_engine", "04_reader_simulation"],
    "detective_psychological": ["09_deep_character_psychology", "10_subtext_engine"],
    "detective_procedural":    ["04_reader_simulation"],
    "detective_action":        ["18_beats_rhythm", "01_tension_curve"],
    "detective_cozy":          ["17_character_chemistry", "15_dialogue_style"],
    "horror_psychological":    ["09_deep_character_psychology", "14_narrative_distance", "16_pov_filters"],
    "horror_cosmic":           ["22_sensory_immersion", "01_tension_curve"],
    "horror_gothic":           ["22_sensory_immersion", "13_foreshadowing_engine"],
    "horror_survival":         ["20_stakes_escalation", "12_pacing_engine"],
    "romance_contemporary":    ["17_character_chemistry", "11_micromoments_library"],
    "romance_historical":      ["17_character_chemistry", "08_world_state_kernel"],
    "romance_paranormal":      ["17_character_chemistry", "22_sensory_immersion"],
    "scifi_cyberpunk":         ["22_sensory_immersion", "10_subtext_engine"],
    "scifi_hard":              ["08_world_state_kernel", "04_reader_simulation"],
    "scifi_social":            ["03_thematic_dna", "04_reader_simulation"],
    "scifi_post_apocalyptic":  ["20_stakes_escalation", "08_world_state_kernel"],
    "realism_psychological":   ["09_deep_character_psychology", "10_subtext_engine"],
    "realism_social":          ["03_thematic_dna", "04_reader_simulation"],
    "realism_family_saga":     ["06_multibook_causality", "17_character_chemistry"],
}

# ─── Бюджет токенов по модели ─────────────────────────────────────────────────

MODEL_TOKEN_BUDGETS = {
    "claude":   180_000,  # Claude 200k — запас на ответ
    "gpt-4o":   110_000,
    "gpt-4":     90_000,
    "gemini":   900_000,  # Gemini 1.5 Pro
    "deepseek": 100_000,
    "default":   90_000,
}

# Лимиты строк по режиму
MODULE_LINE_LIMITS = {
    "quick":   30,   # только суть
    "quality": 50,
    "master":  70,   # почти полная версия
}

# Приоритеты резки при превышении бюджета (меньше = режется первым)
MODULE_PRIORITY = {
    # Высший — режутся последними
    "19_hooks_closings":        10,
    "01_tension_curve":         10,
    "07_voice_consistency":      9,
    "12_pacing_engine":          9,
    "10_subtext_engine":         8,
    # Средний
    "17_character_chemistry":    7,
    "20_stakes_escalation":      7,
    "24_artistic_foundation":    7,
    "22_sensory_immersion":      6,
    "09_deep_character_psychology": 6,
    "02_character_resonance":    6,
    "23_literary_craft":         6,
    "13_foreshadowing_engine":   5,
    "15_dialogue_style":         5,
    "18_beats_rhythm":           5,
    "11_micromoments_library":   5,
    "21_voice_constructor":      5,
    # Низший — режутся первыми
    "08_world_state_kernel":     4,
    "03_thematic_dna":           4,
    "14_narrative_distance":     4,
    "16_pov_filters":            4,
    "25_style_transformations":  4,
    "06_multibook_causality":    3,
    "04_reader_simulation":      3,
    "05_commercial_heatmap":     2,
}


# ─── Жанровые маппинги (единственное место для обновления при добавлении жанра) ──

# Жанровый контракт: семейство → файл контракта
CONTRACT_MAP: dict[str, str] = {
    "fantasy":   "fantasy_contracts.md",
    "detective": "detective_contracts.md",
    "horror":    "horror_contracts.md",
    "romance":   "romance_contracts.md",
    "scifi":     "scifi_contracts.md",
    "thriller":  "thriller_contracts.md",
    "realism":   "realism_contracts.md",
}

# Поджанр → метка в файле контракта.
# Метка ищется подстрокой в заголовках «## » файла 16_GENRE_CONTRACT/<семейство>_contracts.md.
# Не нашлась — загрузчик отдаёт начало файла, то есть контракт ДРУГОГО поджанра;
# это ловит tests/test_unified_contract.py.
SUBGENRE_CONTRACT_LABELS: dict[str, str] = {
    "fantasy_dark":            "ТЁМНОЕ ФЭНТЕЗИ",
    "fantasy_epic":            "ЭПИЧЕСКОЕ ФЭНТЕЗИ",
    "fantasy_urban":           "ГОРОДСКОЕ ФЭНТЕЗИ",
    "fantasy_romantic":        "РОМАНТИЧЕСКОЕ ФЭНТЕЗИ",
    "fantasy_sword_sorcery":   "МЕЧ И МАГИЯ",
    "detective_noir":          "НУАР",
    "detective_classic":       "КЛАССИЧЕСКИЙ",
    "detective_procedural":    "ПРОЦЕДУРАЛ",
    "detective_psychological": "ПСИХОЛОГИЧЕСКИЙ",
    "detective_action":        "ЭКШЕН",
    "detective_cozy":          "COZY",           # общий раздел «КЛАССИЧЕСКИЙ / COZY»
    "horror_cosmic":           "КОСМИЧЕСКИЙ",
    "horror_gothic":           "ГОТИЧЕСКИЙ",
    "horror_psychological":    "ПСИХОЛОГИЧЕСКИЙ",
    "horror_survival":         "ХОРРОР ВЫЖИВАНИЯ",
    "thriller_psychological":  "ПСИХОЛОГИЧЕСКИЙ",
    "thriller_spy":            "ШПИОНСКИЙ",
    "thriller_survival":       "ТРИЛЛЕР ВЫЖИВАНИЯ",
    "romance_contemporary":    "СОВРЕМЕННАЯ РОМАНТИКА",
    "romance_historical":      "ИСТОРИЧЕСКАЯ РОМАНТИКА",
    "romance_paranormal":      "ПАРАНОРМАЛЬНАЯ РОМАНТИКА",
    "scifi_hard":              "ТВЁРДАЯ НФ",
    "scifi_cyberpunk":         "КИБЕРПАНК",
    "scifi_space_opera":       "КОСМИЧЕСКАЯ ОПЕРА",
    "scifi_post_apocalyptic":  "ПОСТАПОКАЛИПСИС",
    "scifi_steampunk":         "СТИМПАНК",
    "scifi_social":            "СОЦИАЛЬНАЯ НФ",
    "realism_psychological":   "ПСИХОЛОГИЧЕСКИЙ",
    "realism_social":          "СОЦИАЛЬНЫЙ",
    "realism_family_saga":     "СЕМЕЙНАЯ САГА",
}

# Полный поджанр → файл профиля персонажа (05_CHARACTER_ENGINE/profiles/GENRE/)
CHAR_FULL_KEY_MAP: dict[str, str] = {
    "detective_noir":          "noir.md",
    "detective_classic":       "detective.md",
    "detective_psychological": "detective.md",
    "detective_procedural":    "detective.md",
    "detective_action":        "detective.md",
    "detective_cozy":          "detective.md",
    "thriller_psychological":  "thriller.md",
    "thriller_spy":            "spy.md",
    "thriller_survival":       "thriller.md",
    "horror_psychological":    "horror.md",
    "horror_cosmic":           "horror.md",
    "horror_gothic":           "horror.md",
    "horror_survival":         "horror.md",
    "fantasy_dark":            "fantasy.md",
    "fantasy_epic":            "epic.md",
    "fantasy_urban":           "urban_mystic.md",
    "fantasy_romantic":        "romance.md",
    "fantasy_sword_sorcery":   "epic.md",
    "romance_contemporary":    "romance.md",
    "romance_historical":      "historical.md",
    "romance_paranormal":      "romance.md",
    "scifi_hard":              "sci_fi.md",
    "scifi_cyberpunk":         "sci_fi.md",
    "scifi_space_opera":       "sci_fi.md",
    "scifi_post_apocalyptic":  "sci_fi.md",
    "scifi_steampunk":         "sci_fi.md",
    "scifi_social":            "sci_fi.md",
    "realism_psychological":   "psychological.md",
    "realism_social":          "psychological.md",
    "realism_family_saga":     "family_drama.md",
}

# Жанровое семейство → файл профиля персонажа (fallback)
CHAR_FAMILY_FALLBACK: dict[str, str] = {
    "detective": "detective.md",
    "thriller":  "thriller.md",
    "horror":    "horror.md",
    "fantasy":   "fantasy.md",
    "romance":   "romance.md",
    "scifi":     "sci_fi.md",
    "realism":   "psychological.md",
}

# Жанровое семейство → ключевое слово для антагониста
ANTAGONIST_GENRE_MAP: dict[str, str] = {
    "detective": "ДЕТЕКТИВ",
    "thriller":  "ТРИЛЛЕР",
    "horror":    "ХОРРОР",
    "fantasy":   "ФЭНТЕЗИ",
    "romance":   "РОМАНТИКА",
    "scifi":     "НФ",
    "realism":   "РЕАЛИЗМ",
}

# ─── Паттерны умного экстрактора ──────────────────────────────────────────────

# Строки которые несут практическую ценность
_VALUABLE_PATTERNS = [
    r'^##',          # заголовки разделов
    r'^###',         # подзаголовки
    r'слабо',        # примеры СЛАБО
    r'сильно',       # примеры СИЛЬНО
    r'запрещ',       # запреты
    r'нельзя',       # тот же запрет другими словами — раньше терялся
    r'никогда',
    r'всегда',
    r'обязательно',
    r'формула',
    r'правил',
    r'принцип',
    r'тип \d',
    r'level \d',
    r'✅',            # замены
    r'❌',            # запреты
    r'→',            # правила
    r'пример',
    r'работает для',
    r'не работает',
    r'эталон',
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _VALUABLE_PATTERNS]

# Строки-метаданные которые нужно пропускать
_SKIP_PATTERNS = [
    re.compile(r'^\*\*Модуль:\*\*'),
    re.compile(r'^\*\*Версия:\*\*'),
    re.compile(r'^\*\*Зависимости:\*\*'),
    re.compile(r'^\*\*Рейтинг:\*\*'),
    re.compile(r'^\*\*Файл:\*\*'),
    re.compile(r'^\*\*Назначение:\*\*'),
    re.compile(r'^---$'),
]
