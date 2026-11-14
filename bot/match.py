"""Сопоставление названий из LMArena с моделями OpenRouter.

Правило простое и осторожное: совпадение засчитывается, только если
совпали и слова, и версия. Лучше показать «—» в цене, чем чужую цену.
Сложные случаи лечатся вручную через aliases.json.
"""

import difflib
import json
import re

from bot.config import ALIASES_PATH, ARENA_ORGS
from bot.sources.openrouter import display_name

_PARENS = re.compile(r"\([^)]*\)")
_VERSION = re.compile(r"\d+(?:\.\d+)*")
_DATE8 = re.compile(r"\b(?:19|20)\d{6}\b")
_DATE_ISO = re.compile(r"\b(?:19|20)\d{2}[-_.]\d{2}[-_.]\d{2}\b")


def norm(text):
    """'Claude Opus 5.5 (High)' -> 'claude opus 5.5'."""
    value = (text or "").lower()
    value = _PARENS.sub(" ", value)
    value = _DATE_ISO.sub(" ", value)
    value = _DATE8.sub(" ", value)
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9.]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def split_parts(normalized):
    """Разделяет имя на слова и версию: 'gpt 5.6 sol' -> ('gpt sol', (5, 6))."""
    words, numbers = [], []
    for token in normalized.split():
        if _VERSION.fullmatch(token):
            numbers.extend(int(part) for part in token.split("."))
        else:
            words.append(token)
    return " ".join(words), tuple(numbers)


def similarity(left, right):
    words_l, version_l = split_parts(left)
    words_r, version_r = split_parts(right)
    if version_l != version_r:
        return 0.0
    if words_l == words_r:
        return 1.0
    ratio = difflib.SequenceMatcher(None, words_l, words_r).ratio()
    return ratio * 0.95 if ratio >= 0.95 else 0.0


def load_aliases():
    try:
        data = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        norm(key): value
        for key, value in data.items()
        if isinstance(value, str) and not key.startswith("_")
    }


def build_index(models):
    index = {}
    for model in models:
        index.setdefault(norm(display_name(model)), []).append(model)
    return index


def find_match(name, org, models, index, aliases, threshold=0.9):
    """Модель OpenRouter для строки рейтинга или None."""
    key = norm(name)
    if not key:
        return None

    alias = aliases.get(key)
    if alias:
        for model in models:
            if model.get("id") == alias:
                return model

    direct = index.get(key)
    if direct:
        return direct[0]

    prefixes = ARENA_ORGS.get((org or "").lower())
    pool = models
    if prefixes:
        narrowed = [m for m in models if (m.get("id") or "").split("/")[0].lower() in prefixes]
        if narrowed:
            pool = narrowed

    best, best_score = None, 0.0
    for model in pool:
        score = similarity(key, norm(display_name(model)))
        if score > best_score:
            best, best_score = model, score
    return best if best_score >= threshold else None
