"""Формирование HTML-сообщений для Telegram."""

from datetime import datetime, timezone

from bot.sources.openrouter import (
    context,
    design_arena_elo,
    display_name,
    input_modalities,
    lab_key,
    lab_name,
    max_output,
    prices,
    reasoning,
    sort_modalities,
)

MOD_NAMES = {
    "text": "текст",
    "image": "фото",
    "file": "файлы",
    "audio": "аудио",
    "video": "видео",
}

MOD_ORDER = ["text", "image", "file", "audio", "video"]


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def money(value):
    if value is None:
        return "—"
    if value == 0:
        return "0"
    if value < 0.01:
        text = f"{value:.4f}"
    elif value < 0.1:
        text = f"{value:.3f}"
    elif value < 100:
        text = f"{value:.2f}"
    else:
        text = f"{value:.0f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def ctx(value):
    if not value:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 1000:
        return f"{round(value / 1000)}K"
    return str(value)


def date_str(timestamp):
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime("%d.%m.%Y")
    except (TypeError, ValueError, OSError):
        return ""


def hashtag(lab):
    return "#" + "".join(ch for ch in lab.replace(" ", "").replace("-", "") if ch.isalnum())


def new_model_post(model, arena=None):
    """Пост о новой модели. arena — строка из рейтинга LMArena или None."""
    name = display_name(model)
    lab = lab_name(model) or lab_key(model).title()
    lines = [f"🆕 <b>{esc(name)}</b>", f"{esc(lab)} · {date_str(model.get('created'))}", ""]

    aa = (arena or {}).get("aa")
    elo = arena.get("elo") if arena else None
    if aa:
        lines.append(f"🧠 Ум: {aa['i']} AA Index · #{aa['r']} в мире")
        if elo:
            lines.append(f"    {round(elo)} Elo · #{arena['rank']} в LMArena")
    elif elo:
        lines.append(f"🧠 Ум: {round(elo)} Elo · #{arena['rank']} в LMArena")
    else:
        lines.append("🧠 Ум: оценок пока нет")

    price = prices(model)
    if price["in"] == 0 and price["out"] == 0:
        lines.append("💵 Бесплатно")
    else:
        lines.append(f"💵 ${money(price['in'])} вход / ${money(price['out'])} выход за 1M")
        if price["cache"]:
            lines.append(f"    кэш: ${money(price['cache'])} за 1M")

    lines.append(f"📏 Контекст: {ctx(context(model))} · ответ до {ctx(max_output(model))}")

    mods = [MOD_NAMES.get(item, item) for item in sort_modalities(input_modalities(model))]
    if mods:
        lines.append("👁 Вход: " + ", ".join(mods))

    reason = reasoning(model)
    if reason:
        efforts = reason.get("supported_efforts") or []
        tail = f" · {'/'.join(efforts)}" if efforts else ""
        lines.append(f"🧩 Reasoning: да{tail}")

    elo = design_arena_elo(model)
    if elo and not (arena and arena.get("elo")):
        lines.append(f"🎨 Design Arena: {round(elo)} Elo")

    lines.append("")
    lines.append(f'🔗 <a href="https://openrouter.ai/{esc(model["id"])}">Открыть на OpenRouter</a>')
    lines.append(hashtag(lab) + " #новый_ии")
    return "\n".join(lines)


def digest_post(models, arena_by_id):
    """Один компактный пост, если за запуск нашлось много моделей."""
    lines = ["🗞 <b>Ещё новые модели</b>", ""]
    for model in models:
        name = display_name(model)
        lab = lab_name(model) or lab_key(model).title()
        price = prices(model)
        tail = "бесплатно" if price["in"] == 0 and price["out"] == 0 else f"${money(price['in'])}/${money(price['out'])}"
        arena = arena_by_id.get(model["id"])
        elo = f" · {round(arena['elo'])} Elo" if arena and arena.get("elo") else ""
        lines.append(f'• <a href="https://openrouter.ai/{esc(model["id"])}">{esc(name)}</a> — {esc(lab)} · {tail}{elo}')
    return "\n".join(lines)


def hello_post():
    return "\n".join(
        [
            "👋 <b>Бот на связи</b>",
            "",
            "Дальше я буду сам писать в канал о новых моделях топ-лабораторий:",
            "цена за 1M токенов, контекст, модальности, оценка LMArena.",
            "",
            "В личке со мной работает:",
            "/top — рейтинг моделей",
            "/new — что вышло за неделю",
            "/model — карточка по названию",
        ]
    )


def recent_item(model, arena=None):
    return {
        "id": model["id"],
        "name": display_name(model),
        "lab": lab_name(model) or lab_key(model).title(),
        "created": int(model.get("created") or 0),
        "elo": round(arena["elo"]) if arena and arena.get("elo") else None,
    }
