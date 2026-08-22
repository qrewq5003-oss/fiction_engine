"""
pipeline_config.py — Декларативная конфигурация pipeline.

Зачем это нужно:
  Вместо процедурного кода с if/else внутри run_pipeline_step(),
  конфигурация описывает ЧТО нужно сделать, а не КАК.
  Шаги можно включать/отключать, менять параметры, собирать пресеты —
  не трогая логику выполнения.

Использование:
  from .pipeline_config import PipelineConfig, STANDARD, QUICK, DEEP

  # Готовый пресет
  result = start_pipeline(..., config=STANDARD)

  # Кастомная конфигурация
  cfg = PipelineConfig(
      steps=[
          StepConfig("generate"),
          StepConfig("critique", max_tokens=1500),
          StepConfig("judge", enabled=False),   # отключить судью
      ],
      max_score_threshold=38,   # принять если судья даёт >= 38/50
      max_iterations=2,
  )
  result = start_pipeline(..., config=cfg)

  # Конфигурация как словарь (для хранения в БД / передачи через API)
  cfg_dict = STANDARD.to_dict()
  cfg = PipelineConfig.from_dict(cfg_dict)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable


# ─── StepConfig ───────────────────────────────────────────────────────────────

@dataclass
class StepConfig:
    """
    Конфигурация одного шага pipeline.

    name       — идентификатор: "generate" | "edit" | "critique" | "judge"
    enabled    — False = шаг пропускается без ошибки
    max_tokens — лимит ответа для этого шага
    model_role — какую модель использовать (gen / critic / editor / judge)
                 None = берётся автоматически по имени шага
    """
    name:       str
    enabled:    bool  = True
    max_tokens: int   = 6000
    model_role: str | None = None   # явный override модели

    def __post_init__(self):
        valid = {"generate", "edit", "critique", "judge"}
        if self.name not in valid:
            raise ValueError(f"Неизвестный шаг: '{self.name}'. Допустимые: {valid}")

    @property
    def default_model_role(self) -> str:
        """Роль модели по умолчанию если model_role не задан явно."""
        return self.model_role or {
            "generate": "gen",
            "edit":     "editor",
            "critique": "critic",
            "judge":    "judge",
        }[self.name]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StepConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─── PipelineConfig ───────────────────────────────────────────────────────────

@dataclass
class PipelineConfig:
    """
    Полная декларативная конфигурация pipeline.

    steps               — список шагов в порядке выполнения
    max_iterations      — максимум кругов generate→critique→judge
    score_threshold     — принять автоматически если judge даёт >= X/50
    accept_on_timeout   — принять последний вариант если кончились итерации
    max_auto_retries    — сколько раз автоматически повторить edit→critique→judge
                          при вердикте «НА ДОРАБОТКУ» (0 = opt-in, выкл. по умолчанию)
    description         — человекочитаемое описание пресета
    """
    steps:              list[StepConfig]
    max_iterations:     int   = 3
    score_threshold:    float = 38.0    # >= 38/50 → ПРИНЯТЬ автоматически
    accept_on_timeout:  bool  = True    # принять лучший вариант по истечении итераций
    max_auto_retries:   int   = 0       # авто-цикл: 0 = отключён (opt-in)
    description:        str   = ""

    @property
    def enabled_steps(self) -> list[StepConfig]:
        return [s for s in self.steps if s.enabled]

    @property
    def step_names(self) -> list[str]:
        return [s.name for s in self.enabled_steps]

    def has_step(self, name: str) -> bool:
        return any(s.name == name and s.enabled for s in self.steps)

    def get_step(self, name: str) -> StepConfig | None:
        return next((s for s in self.steps if s.name == name), None)

    def with_step_disabled(self, name: str) -> "PipelineConfig":
        """Вернуть новый конфиг с отключённым шагом (иммутабельно)."""
        new_steps = [
            StepConfig(s.name, enabled=False if s.name == name else s.enabled,
                       max_tokens=s.max_tokens, model_role=s.model_role)
            for s in self.steps
        ]
        import dataclasses
        return dataclasses.replace(self, steps=new_steps)

    def to_dict(self) -> dict:
        return {
            "steps":             [s.to_dict() for s in self.steps],
            "max_iterations":    self.max_iterations,
            "score_threshold":   self.score_threshold,
            "accept_on_timeout": self.accept_on_timeout,
            "max_auto_retries":  self.max_auto_retries,
            "description":       self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineConfig":
        steps = [StepConfig.from_dict(s) for s in d.get("steps", [])]
        return cls(
            steps=steps,
            max_iterations=d.get("max_iterations", 3),
            score_threshold=d.get("score_threshold", 38.0),
            accept_on_timeout=d.get("accept_on_timeout", True),
            max_auto_retries=d.get("max_auto_retries", 0),
            description=d.get("description", ""),
        )

    def to_pipeline_steps(self):
        """
        Конвертировать в список PipelineStep для _execute_steps().
        Совместимость с pipeline.py.
        """
        from .pipeline import PipelineStep
        return [PipelineStep(s.name, s.enabled) for s in self.steps]


# ─── Бюджет вывода под объём главы ────────────────────────────────────────────
#
# Промпты (state_prompts.py) требуют «СТРОГО 2500-3000 слов».
# Русский текст дорог в токенах: на реальной главе проекта — 6.8 символа на
# слово, а кириллица укладывается примерно в 2.0-2.5 символа на токен.
#
#   3000 слов × 6.8 симв. = 20 400 симв. → 8 200 … 10 200 токенов
#   2500 слов × 6.8 симв. = 17 000 симв. → 6 800 …  8 500 токенов
#
# Прежние значения (generate=8000, edit=7000) лежали НИЖЕ этого диапазона:
# модель упиралась в потолок и глава обрывалась на середине фразы. Причём
# edit был меньше generate — то есть редактура резала главу, которую
# генерация успела написать целиком.
#
# max_tokens — это потолок, а не предоплата: счёт идёт за реально выданные
# токены, поэтому запас ничего не стоит.

TARGET_CHAPTER_WORDS = 3000          # верх требования из промптов
RU_CHARS_PER_WORD    = 6.8           # замер на реальных главах проекта
RU_CHARS_PER_TOKEN   = 2.0           # консервативная оценка для кириллицы
PROSE_HEADROOM       = 1.15          # заголовок, разбивка, хвост фразы


def tokens_for_words(words: int = TARGET_CHAPTER_WORDS) -> int:
    """Сколько токенов вывода нужно, чтобы уместить главу заданного объёма."""
    chars = words * RU_CHARS_PER_WORD
    return int(chars / RU_CHARS_PER_TOKEN * PROSE_HEADROOM)


# Единый потолок для шагов, которые выдают полный текст главы.
# generate и edit обязаны быть равны: иначе редактура обрежет генерацию.
PROSE_MAX_TOKENS = tokens_for_words()          # ≈ 11 700

# Минимальный приемлемый объём — ниже него глава считается недописанной.
MIN_ACCEPTABLE_WORDS = 2000

# Оценка размера промпта. Прежний код считал len(text) // 4 — это отношение
# для английского. На русско-язычном контексте оно занижает число токенов
# примерно в полтора раза, поэтому защита от переполнения окна срабатывала
# слишком поздно. 3.0 — компромисс: кириллица ~2.0-2.5, разметка и латиница ~4.
MIXED_CHARS_PER_TOKEN = 3.0


def estimate_tokens(text: str) -> int:
    """Грубая оценка числа токенов в смешанном русско-английском тексте."""
    return int(len(text) / MIXED_CHARS_PER_TOKEN)


# ─── Пресеты ──────────────────────────────────────────────────────────────────

QUICK = PipelineConfig(
    description="Быстрый черновик: генерация + критика, без редактуры и судьи",
    max_iterations=1,
    score_threshold=999,        # никогда не авто-принимает
    steps=[
        StepConfig("generate", max_tokens=PROSE_MAX_TOKENS),
        StepConfig("critique", max_tokens=1500),
        StepConfig("judge",    enabled=False),
    ],
)

STANDARD = PipelineConfig(
    description="Стандарт: генерация → критика → судья, до 2 итераций",
    max_iterations=2,
    score_threshold=38.0,
    steps=[
        StepConfig("generate", max_tokens=PROSE_MAX_TOKENS),
        StepConfig("critique", max_tokens=2000),
        StepConfig("judge",    max_tokens=2000),
    ],
)

DEEP = PipelineConfig(
    description="Глубокий: генерация → критика → редактура → судья, до 3 итераций",
    max_iterations=3,
    score_threshold=42.0,
    steps=[
        StepConfig("generate", max_tokens=PROSE_MAX_TOKENS),
        StepConfig("critique", max_tokens=2000),
        StepConfig("edit",     max_tokens=PROSE_MAX_TOKENS),
        StepConfig("judge",    max_tokens=2000),
    ],
)

CRITIQUE_ONLY = PipelineConfig(
    description="Только критика готового текста, без генерации",
    max_iterations=1,
    score_threshold=999,
    steps=[
        StepConfig("generate", enabled=False),
        StepConfig("critique", max_tokens=2000),
        StepConfig("judge",    max_tokens=2000),
    ],
)

# Пресет для второго и последующих кругов (continue_pipeline)
CONTINUE = PipelineConfig(
    description="Продолжение: редактура по критике → повторная критика → судья",
    max_iterations=1,
    score_threshold=38.0,
    steps=[
        StepConfig("edit",     max_tokens=PROSE_MAX_TOKENS),
        StepConfig("critique", max_tokens=2000),
        StepConfig("judge",    max_tokens=2000),
    ],
)

# Авто-улучшение: generate → critique → judge, и если НА ДОРАБОТКУ —
# автоматически edit → critique → judge (до 2 раз).
# Каждый авто-retry = 3 LLM вызова. Потенциально 9 вызовов всего.
# Защита от деградации: retry прерывается если score не растёт.
AUTO_IMPROVE = PipelineConfig(
    description="Авто-улучшение: до 2 авто-повторов edit→critique→judge при НА ДОРАБОТКУ",
    max_iterations=3,
    score_threshold=38.0,
    max_auto_retries=2,
    steps=[
        StepConfig("generate", max_tokens=PROSE_MAX_TOKENS),
        StepConfig("critique", max_tokens=2000),
        StepConfig("judge",    max_tokens=2000),
    ],
)


# ─── Реестр пресетов ──────────────────────────────────────────────────────────

PRESETS: dict[str, PipelineConfig] = {
    "quick":         QUICK,
    "standard":      STANDARD,
    "deep":          DEEP,
    "critique_only": CRITIQUE_ONLY,
    "continue":      CONTINUE,
    "auto_improve":  AUTO_IMPROVE,
}


def get_preset(name: str) -> PipelineConfig:
    """
    Получить пресет по имени. Бросает ValueError для неизвестного имени.
    Используется в web/CLI для передачи конфига как строки.
    """
    if name not in PRESETS:
        raise ValueError(
            f"Неизвестный пресет '{name}'. Доступные: {list(PRESETS)}"
        )
    return PRESETS[name]


def list_presets() -> list[dict]:
    """Список всех пресетов для UI."""
    return [
        {
            "id":          name,
            "description": cfg.description,
            "steps":       cfg.step_names,
            "max_iter":    cfg.max_iterations,
        }
        for name, cfg in PRESETS.items()
    ]
