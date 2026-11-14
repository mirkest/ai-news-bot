"""Меню команд, описание и короткое описание бота в Telegram.

Запускается из workflow раз в сутки, чтобы меню всегда совпадало с кодом.
"""

import os
import sys

from bot.http import post_json

API = "https://api.telegram.org/bot{token}/{method}"

COMMANDS = [
    {"command": "start", "description": "Что умеет бот и все команды"},
    {"command": "top", "description": "Рейтинг моделей: Elo, цены, контекст"},
    {"command": "new", "description": "Новые модели за 7 дней"},
    {"command": "model", "description": "Карточка модели по названию"},
    {"command": "help", "description": "Как это работает и откуда данные"},
]

DESCRIPTION = (
    "Новые ИИ, цены за 1M токенов, контекст и рейтинг LMArena. "
    "Посты о релизах — в канале, рейтинг — командой /top."
)

SHORT_DESCRIPTION = "Новые ИИ: цены, контекст, рейтинг LMArena"


def main():
    token = "".join(os.environ.get("TELEGRAM_BOT_TOKEN", "").split())
    if not token:
        raise SystemExit("Нужен TELEGRAM_BOT_TOKEN")

    calls = [
        ("setMyCommands", {"commands": COMMANDS}),
        ("setMyDescription", {"description": DESCRIPTION}),
        ("setMyShortDescription", {"short_description": SHORT_DESCRIPTION}),
    ]
    for method, payload in calls:
        result = post_json(API.format(token=token, method=method), payload)
        status = "ok" if result.get("ok") else result.get("description")
        print(f"[setup] {method}: {status}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
