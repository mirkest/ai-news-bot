"""Тонкая обёртка над urllib: ретраи, таймауты, JSON."""

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "ai-news-bot/1.0 (github actions)"


def _request(url, data=None, timeout=30):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_bytes(url, timeout=30, retries=3, backoff=3):
    """Скачать URL с ретраями."""
    last = None
    for attempt in range(retries):
        try:
            return _request(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 — нужен любой сбой сети/сервера
            last = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise last


def get_json(url, timeout=30, retries=3):
    return json.loads(get_bytes(url, timeout=timeout, retries=retries).decode("utf-8"))


def post_json(url, payload, timeout=30, retries=2):
    """POST JSON. Возвращает распарсенный ответ или бросает исключение."""
    last = None
    for attempt in range(retries):
        try:
            return json.loads(_request(url, data=payload, timeout=timeout).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 400 от Telegram содержит описание ошибки — оно полезнее кода ответа.
            try:
                return json.loads(exc.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                last = exc
        except Exception as exc:  # noqa: BLE001
            last = exc
        if attempt < retries - 1:
            time.sleep(2)
    raise last
