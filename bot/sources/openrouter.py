"""Модели, цены и характеристики из OpenRouter (без ключа)."""

from bot.config import LABS
from bot.http import get_json

MODELS_URL = "https://openrouter.ai/api/v1/models"


def fetch_models():
    """Список всех моделей OpenRouter."""
    return get_json(MODELS_URL, timeout=60)["data"]


def lab_key(model):
    """Префикс id: 'anthropic/claude-x' -> 'anthropic'."""
    return (model.get("id") or "").split("/", 1)[0].lower()


def lab_name(model):
    """Человеческое имя лаборатории или None, если её нет в списке."""
    return LABS.get(lab_key(model))


def is_lab(model):
    return lab_key(model) in LABS


def display_name(model):
    """'Anthropic: Claude Fable 5.2' -> 'Claude Fable 5.2'."""
    name = (model.get("name") or model.get("id") or "").strip()
    if ": " in name:
        name = name.split(": ", 1)[1]
    return name


def per_million(value):
    """Цена за токен (строка) -> цена за 1M токенов."""
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None


def prices(model):
    pricing = model.get("pricing") or {}
    return {
        "in": per_million(pricing.get("prompt")),
        "out": per_million(pricing.get("completion")),
        "cache": per_million(pricing.get("input_cache_read")),
    }


def context(model):
    return model.get("context_length") or (model.get("top_provider") or {}).get("context_length")


def max_output(model):
    return (model.get("top_provider") or {}).get("max_completion_tokens")


def input_modalities(model):
    arch = model.get("architecture") or {}
    mods = arch.get("input_modalities") or []
    if not mods and arch.get("modality"):
        mods = arch["modality"].split("->")[0].split("+")
    return [str(m).lower() for m in mods if m]


MOD_ORDER = ["text", "image", "file", "audio", "video"]


def sort_modalities(mods):
    """Стабильный порядок иконок: текст, фото, файлы, аудио, видео."""
    known = [item for item in MOD_ORDER if item in mods]
    return known + [item for item in mods if item not in MOD_ORDER]


def reasoning(model):
    """Описание reasoning-режима или None."""
    data = model.get("reasoning")
    if not data:
        return None
    if isinstance(data, list):
        efforts = [str(x) for x in data if isinstance(x, str)]
        return {"mandatory": False, "supported_efforts": efforts} if efforts else None
    if isinstance(data, dict):
        return data
    return None


def design_arena_elo(model):
    """Запасной показатель «ума» из бенчмарков OpenRouter (Design Arena)."""
    rows = (model.get("benchmarks") or {}).get("design_arena") or []
    elos = [r.get("elo") for r in rows if isinstance(r.get("elo"), (int, float))]
    return max(elos) if elos else None
