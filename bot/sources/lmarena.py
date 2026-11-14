"""Рейтинг LMArena из открытого датасета на Hugging Face (без ключа).

Порядок попыток для каждой конфигурации:
1. parquet-файл (нужен pyarrow, зато работает, даже когда вьюер HF лежит);
2. JSON-вьюер datasets-server (без зависимостей, но иногда отдаёт 501).

Если не вышло ни то, ни другое — пробуем следующую конфигурацию.
"""

import io
from urllib.parse import quote

from bot.http import get_bytes, get_json

DATASET = "lmarena-ai/leaderboard-dataset"
ROWS_API = "https://datasets-server.huggingface.co/rows"
PARQUET_API = "https://datasets-server.huggingface.co/parquet"
SPLIT = "latest"
PAGE = 100
MAX_ROWS = 900
OVERALL_TARGET = 500

# В датасете LMArena основная текстовая доска называется text_style_control:
# конфигурации с именем "text" больше нет. Если появится — её можно добавить сюда.
CONFIGS = ("text_style_control",)


def _rows_from_api(config):
    rows = []
    offset = 0
    while offset < MAX_ROWS:
        url = (
            f"{ROWS_API}?dataset={quote(DATASET, safe='')}&config={config}"
            f"&split={SPLIT}&offset={offset}&length={PAGE}"
        )
        page = get_json(url, timeout=45)
        batch = page.get("rows") or []
        if not batch:
            break
        rows.extend(item.get("row") or {} for item in batch)
        offset += len(batch)
        total = page.get("num_rows_total") or 0
        if total and offset >= total:
            break
        if sum(1 for row in rows if row.get("category") == "overall") >= OVERALL_TARGET:
            break
    return rows


def _rows_from_parquet(config):
    import pyarrow.parquet as pq  # тяжёлая зависимость, импортируем только здесь

    index = get_json(f"{PARQUET_API}?dataset={quote(DATASET, safe='')}", timeout=45)
    url = next(
        (
            item["url"]
            for item in index.get("parquet_files", [])
            if item.get("config") == config and item.get("split") == SPLIT
        ),
        None,
    )
    if not url:
        raise RuntimeError(f"нет parquet для конфигурации {config}")
    raw = get_bytes(url, timeout=90, retries=2)
    return pq.read_table(io.BytesIO(raw)).to_pylist()


def fetch_leaderboard():
    """Возвращает (конфигурация, строки категории overall, дата публикации)."""
    errors = []
    for config in CONFIGS:
        for loader in (_rows_from_parquet, _rows_from_api):
            try:
                rows = loader(config)
            except Exception as exc:  # noqa: BLE001 — источник необязательный, пробуем дальше
                errors.append(f"{config}/{loader.__name__}: {exc}")
                continue
            overall = [row for row in rows if (row.get("category") or "") == "overall"]
            if overall and "rating" in overall[0]:
                date = max(
                    (row.get("leaderboard_publish_date") for row in overall if row.get("leaderboard_publish_date")),
                    default="",
                )
                return config, overall, date
            errors.append(f"{config}/{loader.__name__}: пусто")
    raise RuntimeError("LMArena недоступна: " + " | ".join(errors))
