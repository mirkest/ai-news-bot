"""Главный цикл: найти новые модели топ-лабораторий и опубликовать их в канал.

Запуск:
    python -m bot.main             # обычный запуск (в Actions)
    python -m bot.main --dry-run   # показать посты в консоли, ничего не отправлять
    python -m bot.main --seed      # только запомнить текущие модели, без постов
"""

import argparse
import json
import os
import re
import sys
import time

from bot.config import (
    AA_WINDOW_DAYS,
    DATA_DIR,
    LEADERBOARD_PATH,
    MAX_POSTS_PER_RUN,
    NEW_WINDOW_DAYS,
    RECENT_DAYS,
    RECENT_PATH,
    STATE_PATH,
)
from bot.format import aa_only_post, digest_post, hello_post, new_model_post, recent_item
from bot.http import post_json
from bot.match import norm
from bot.sources import openrouter

API = "https://api.telegram.org/bot{token}/{method}"
DATED_SLUG = re.compile(r"-\d{8}$")
PENDING_MAX_AGE = 14 * 86400
PENDING_LIMIT = 20


# ---------------------------------------------------------------- состояние


def load_state():
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("ids", [])
    data.setdefault("slugs", [])
    data.setdefault("pending", [])
    data.setdefault("announced", False)
    return data


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def slug_base(model):
    """'anthropic/claude-x-20261112' -> 'anthropic/claude-x'."""
    slug = (model.get("canonical_slug") or model.get("id") or "").split(":")[0]
    return DATED_SLUG.sub("", slug)


# ---------------------------------------------------------------- Telegram


def send_message(token, chat_id, text):
    data = post_json(
        API.format(token=token, method="sendMessage"),
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        },
    )
    if not data.get("ok"):
        raise RuntimeError(f"sendMessage: {data.get('description')}")
    return data["result"]["message_id"]


def edit_message(token, chat_id, message_id, text):
    return post_json(
        API.format(token=token, method="editMessageText"),
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        },
    )


# ---------------------------------------------------------------- данные


def load_board():
    """Рейтинг LMArena: id модели OpenRouter -> строка рейтинга."""
    try:
        data = json.loads(LEADERBOARD_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {entry["or"]: entry for entry in data.get("models", []) if entry.get("or")}


def find_new(models, state):
    seen_ids = set(state["ids"])
    seen_slugs = set(state["slugs"])
    now = time.time()
    fresh = []
    for model in models:
        model_id = model.get("id") or ""
        if not model_id or model_id in seen_ids:
            continue
        if ":" in model_id:  # :free, :batch, :thinking и прочие варианты той же модели
            continue
        if slug_base(model) in seen_slugs:
            continue
        if now - (model.get("created") or 0) > NEW_WINDOW_DAYS * 86400:
            continue
        if not openrouter.is_lab(model):
            continue
        fresh.append(model)
    return sorted(fresh, key=lambda model: model.get("created") or 0)


def find_aa_new(board, state, days=AA_WINDOW_DAYS):
    """Модели, которые AA уже оценил, но OpenRouter ещё не принёс.

    Это второй детектор: он ловит релизы, до которых OpenRouter не добрался,
    но с задержкой — рейтинг пересобирается раз в несколько часов.
    """
    seen = set(state.get("aa_seen") or [])
    known = set(state.get("ids") or [])
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    found = []
    for entry in board.values():
        release = entry.get("rel")
        if not release or release < cutoff:
            continue
        or_id = entry.get("or")
        if or_id and or_id in known:
            continue  # OpenRouter уже видел эту модель — пост по ней был или будет
        key = or_id or "n:" + norm(entry.get("name") or "")
        if key in seen:
            continue
        found.append(entry)
    return found


def update_recent(models_by_id, board):
    try:
        data = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"items": []}
    items = {item["id"]: item for item in data.get("items", [])}
    threshold = time.time() - RECENT_DAYS * 86400
    for model_id, model in models_by_id.items():
        arena = board.get(model_id)
        items[model_id] = recent_item(model, arena)
    data["items"] = sorted(
        [item for item in items.values() if (item.get("created") or 0) >= threshold],
        key=lambda item: -(item.get("created") or 0),
    )[:40]
    data["updated"] = time.strftime("%Y-%m-%d", time.gmtime())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RECENT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def refresh_pending(token, chat_id, state, board):
    """Дописывает Elo в посты, которые вышли до появления оценки."""
    alive, changed = [], False
    for item in state["pending"]:
        if time.time() - item.get("ts", 0) > PENDING_MAX_AGE:
            changed = True
            continue
        arena = board.get(item.get("or"))
        if not arena:
            alive.append(item)
            continue
        model = item["model"]
        try:
            edit_message(token, item["chat_id"], item["message_id"], new_model_post(model, arena))
            print(f"[pending] дописана оценка: {model.get('id')}")
        except Exception as exc:  # noqa: BLE001 — сообщение могли удалить
            print(f"[pending] не удалось обновить {model.get('id')}: {exc}")
        changed = True
    state["pending"] = alive[:PENDING_LIMIT]
    return changed


# ---------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()

    dry_run = args.dry_run or os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"}
    token = "".join(os.environ.get("TELEGRAM_BOT_TOKEN", "").split())
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not dry_run and (not token or not chat_id):
        raise SystemExit("Нужны TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")

    state = load_state()
    models = openrouter.fetch_models()
    board = load_board()

    first_run = not state["ids"] or args.seed
    if first_run:
        state["ids"] = sorted(model["id"] for model in models)
        state["slugs"] = sorted({slug_base(model) for model in models})
        state["aa_seen"] = sorted(
            entry.get("or") or "n:" + norm(entry.get("name") or "")
            for entry in board.values()
            if entry.get("rel")
        )
        if not state["announced"]:
            text = hello_post()
            if dry_run:
                print("\n===== приветствие =====\n" + text)
            else:
                send_message(token, chat_id, text)
            state["announced"] = True
        print(f"[seed] запомнил {len(state['ids'])} моделей, постов не будет")
        if not dry_run:
            save_state(state)
        return

    fresh = find_new(models, state)
    by_id = {model["id"]: model for model in models}
    fresh_ids = {model["id"] for model in fresh}

    queue = [(model, board.get(model["id"])) for model in fresh]
    aa_extra = 0
    for entry in find_aa_new(board, state):
        or_id = entry.get("or")
        if or_id and or_id in fresh_ids:
            continue
        queue.append((by_id.get(or_id) if or_id else None, entry))
        aa_extra += 1
    print(f"[new] OpenRouter: {len(fresh)}, Artificial Analysis: {aa_extra}")

    posts, digest = queue[:MAX_POSTS_PER_RUN], queue[MAX_POSTS_PER_RUN:]
    if len(digest) == 1:
        posts, digest = queue, []

    for model, arena in posts:
        text = new_model_post(model, arena) if model else aa_only_post(arena)
        if dry_run:
            print("\n===== пост =====\n" + text)
            continue
        message_id = send_message(token, chat_id, text)
        print(f"[post] {model['id'] if model else arena.get('name')} -> message {message_id}")
        if model and not arena:
            state["pending"].append(
                {
                    "or": model["id"],
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "ts": int(time.time()),
                    "model": model,
                }
            )

    if digest:
        text = digest_post(digest)
        if dry_run:
            print("\n===== дайджест =====\n" + text)
        else:
            send_message(token, chat_id, text)
            print(f"[digest] {len(digest)} моделей")

    if not dry_run:
        state["ids"] = sorted(set(state["ids"]) | {model["id"] for model in models})
        state["slugs"] = sorted(set(state["slugs"]) | {slug_base(model) for model in models})
        state["ids"] = state["ids"][-5000:]
        state["slugs"] = state["slugs"][-5000:]
        state["aa_seen"] = sorted(
            set(state.get("aa_seen") or [])
            | {
                entry.get("or") or "n:" + norm(entry.get("name") or "")
                for entry in board.values()
                if entry.get("rel")
            }
        )[-5000:]
        update_recent({model["id"]: model for model in models}, board)
        if chat_id:
            refresh_pending(token, chat_id, state, board)
        save_state(state)
    else:
        print("\n[dry-run] состояние не изменено")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    main()
