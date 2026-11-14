"""Сборка data/leaderboard.json — рейтинга LMArena с ценами OpenRouter.

Запуск: python -m bot.build_leaderboard [--if-stale 20h]
"""

import argparse
import json
import os
import sys
import time

from bot.config import (
    ARENA_ORGS,
    DATA_DIR,
    LEADERBOARD_PATH,
    ORG_NAMES,
    UNMATCHED_PATH,
)
from bot.match import build_index, find_match, load_aliases, norm
from bot.sources import aa, lmarena, openrouter


LEADERBOARD_SCHEMA = 5  # меняется, когда формат файла требует пересборки


def _org_name(org):
    key = (org or "").strip().lower()
    return ORG_NAMES.get(key, (org or "").strip().title())


def _is_lab_org(org):
    value = (org or "").strip().lower()
    return value in ARENA_ORGS or any(key.replace("-", " ") in value for key in ARENA_ORGS)


def _best_rows(rows):
    """Схлопывает варианты одной модели ((High), (Max), без суффикса)."""
    best = {}
    for row in rows:
        name = row.get("model_name") or ""
        if not name:
            continue
        key = ((row.get("organization") or "").lower(), norm(name))
        current = best.get(key)
        if current is None or (row.get("rating") or 0) > (current.get("rating") or 0):
            best[key] = row
    return sorted(best.values(), key=lambda row: -(row.get("rating") or 0))


def build():
    models = openrouter.fetch_models()
    index = build_index(models)
    aliases = load_aliases()

    try:
        config, rows, board_date = lmarena.fetch_leaderboard()
    except Exception as exc:  # noqa: BLE001 — без рейтинга отдаём хотя бы пустую заготовку
        print(f"[leaderboard] LMArena недоступна: {exc}", file=sys.stderr)
        raise SystemExit(1)

    ordered = _best_rows(rows)
    entries, unmatched = [], []

    aa_models = aa.scored(aa.fetch_models())
    aa_models.sort(key=lambda item: -item["index"])
    for place, item in enumerate(aa_models, start=1):
        item["place"] = place

    aa_pairs = []
    for item in aa_models:
        match = find_match(item["name"], item["creator"].lower(), models, index, aliases)
        if match:
            aa_pairs.append((match["id"], item))

    aa_by_or = {}
    for or_id, item in aa_pairs:
        aa_by_or.setdefault(or_id, item)
    print(f"[aa] моделей с индексом: {len(aa_models)}, сопоставлено: {len(aa_pairs)}")

    for rank, row in enumerate(ordered, start=1):
        name = (row.get("model_name") or "").strip()
        org = (row.get("organization") or "").strip()
        match = find_match(name, org, models, index, aliases)

        entry = {
            "rank": rank,
            "name": name,
            "org": _org_name(org),
            "elo": round(float(row.get("rating") or 0), 1),
            "votes": int(row.get("vote_count") or 0),
            "lab": False,
        }

        if match:
            price = openrouter.prices(match)
            entry.update(
                {
                    "in": None if price["in"] is None else round(price["in"], 4),
                    "out": None if price["out"] is None else round(price["out"], 4),
                    "ctx": openrouter.context(match),
                    "mods": openrouter.sort_modalities(openrouter.input_modalities(match)),
                    "or": match["id"],
                    "lab": openrouter.is_lab(match),
                }
            )
            aa_item = aa_by_or.get(match["id"])
            if aa_item:
                entry["aa"] = {
                    "i": round(aa_item["index"], 1),
                    "r": aa_item["place"],
                }
                entry["rel"] = aa_item.get("release")
        else:
            entry["lab"] = _is_lab_org(org)
            if rank <= 150:
                unmatched.append({"rank": rank, "name": name, "org": org})

        entries.append(entry)

    # Модели, которые есть у Artificial Analysis, но ещё не попали в LMArena:
    # именно они самые свежие, поэтому без них рейтинг «ума» неполный.
    by_id = {model["id"]: model for model in models}
    covered = {entry["or"] for entry in entries if entry.get("or")}
    extra = 0
    for or_id, item in aa_by_or.items():
        if or_id in covered:
            continue
        model = by_id.get(or_id)
        if not model:
            continue
        price = openrouter.prices(model)
        entries.append(
            {
                "rank": None,
                "name": openrouter.display_name(model),
                "org": item["creator"] or _org_name(openrouter.lab_key(model)),
                "elo": None,
                "votes": 0,
                "lab": openrouter.is_lab(model),
                "in": None if price["in"] is None else round(price["in"], 4),
                "out": None if price["out"] is None else round(price["out"], 4),
                "ctx": openrouter.context(model),
                "mods": openrouter.sort_modalities(openrouter.input_modalities(model)),
                "or": or_id,
                "aa": {"i": round(item["index"], 1), "r": item["place"]},
                "rel": item.get("release"),
            }
        )
        extra += 1
    print(f"[aa] добавлено моделей без LMArena: {extra}")

    # Совсем новые модели: есть у AA, но их ещё нет в OpenRouter.
    # Постить их можно, только показывая индекс и цену из AA.
    covered_names = {norm(entry["name"]) for entry in entries}
    unmatched_aa = 0
    for item in aa_models:
        if norm(item["name"]) in covered_names:
            continue
        entries.append(
            {
                "rank": None,
                "name": item["name"],
                "org": item["creator"] or "",
                "elo": None,
                "votes": 0,
                "lab": _is_lab_org(item["creator"]),
                "aa": {"i": round(item["index"], 1), "r": item["place"]},
                "rel": item.get("release"),
                "aa_in": item.get("price_in"),
                "aa_out": item.get("price_out"),
            }
        )
        unmatched_aa += 1
    print(f"[aa] моделей вне OpenRouter: {unmatched_aa}")

    payload = {
        "updated": time.strftime("%Y-%m-%d", time.gmtime()),
        "fetched_at": int(time.time()),
        "schema": LEADERBOARD_SCHEMA,
        "board": config,
        "board_date": board_date,
        "aa_count": len(aa_models),
        "source": "Artificial Analysis + LMArena + OpenRouter pricing",
        "models": entries,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LEADERBOARD_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    if unmatched:
        UNMATCHED_PATH.write_text(
            json.dumps(unmatched, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    matched = sum(1 for entry in entries if entry.get("or"))
    print(
        f"[leaderboard] {len(entries)} моделей, цен найдено у {matched}, "
        f"источник {config}, обновлено {board_date or payload['updated']}"
    )


def is_stale(spec):
    if not LEADERBOARD_PATH.exists():
        return True
    try:
        hours = float(str(spec).rstrip("h"))
    except ValueError:
        return True
    try:
        data = json.loads(LEADERBOARD_PATH.read_text(encoding="utf-8"))
        fetched_at = int(data.get("fetched_at") or 0)
    except (OSError, ValueError):
        return True
    # Появился ключ Artificial Analysis, а рейтинг собран без него — пересобираем сразу.
    if os.environ.get("AA_API_KEY") and not data.get("aa_count"):
        return True
    if data.get("schema") != LEADERBOARD_SCHEMA:
        return True
    return time.time() - fetched_at > hours * 3600


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-stale", default=None, help="пересобрать, только если старше, например 20h")
    args = parser.parse_args()
    if args.if_stale and not is_stale(args.if_stale):
        print("[leaderboard] свежий, пересборка не нужна")
        return
    build()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    main()
