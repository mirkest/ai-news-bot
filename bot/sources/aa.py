"""Artificial Analysis: Intelligence Index и скорость модели.

Бесплатный тариф отдаёт до 200 моделей на страницу, поэтому за один запуск
уходит 3–4 запроса из 100 дневных. Без ключа модуль молча ничего не делает.
"""

import os

from bot.http import get_json

BASE = "https://artificialanalysis.ai/api/v2/language/models/free"
PAGE_SIZE = 200
MAX_PAGES = 6
FIELD = "artificial_analysis_intelligence_index"


def fetch_models(api_key=None):
    """Список моделей AA или [] , если ключа нет или источник недоступен."""
    key = (api_key or os.environ.get("AA_API_KEY") or "").strip()
    if not key:
        return []

    headers = {"x-api-key": key}
    models = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE}?page={page}&page_size={PAGE_SIZE}"
        try:
            payload = get_json(url, timeout=60, headers=headers)
        except Exception as exc:  # noqa: BLE001 — источник необязательный
            print(f"[aa] страница {page} недоступна: {exc}")
            break
        batch = payload.get("data") or []
        if not batch:
            break
        models.extend(batch)
        if not (payload.get("pagination") or {}).get("has_more"):
            break
    return models


def scored(models):
    """Только модели с непустым Intelligence Index."""
    result = []
    for model in models:
        value = (model.get("evaluations") or {}).get(FIELD)
        if value is None:
            continue
        performance = model.get("performance") or {}
        result.append(
            {
                "name": model.get("name") or "",
                "creator": ((model.get("model_creator") or {}).get("name") or ""),
                "index": float(value),
                "speed": performance.get("mean_output_tokens_per_second"),
                "release": model.get("release_date"),
            }
        )
    return result
