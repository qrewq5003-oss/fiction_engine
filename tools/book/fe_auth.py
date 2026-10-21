"""Доступ инструментов книги к Fiction Engine: токен и сессия с тайм-аутом.

Токен — как у планировщика (fiction_engine/web/security.api_token): из
FE_PASSWORD, если он задан, иначе файл FE_API_TOKEN_FILE или
~/fiction_engine/api_token. Раньше инструменты читали только файл — с
паролем в .env их запросы получали 401 (разбор 21.10).
"""
import hashlib
import os
from pathlib import Path

import requests

DEFAULT_TIMEOUT = 600        # вызов модели по подписке идёт минутами; без тайм-аута — вечно


def token() -> str:
    pw = os.environ.get("FE_PASSWORD", "")
    if pw:
        return hashlib.sha256(("fiction-engine-api:" + pw).encode()).hexdigest()
    path = Path(os.environ.get("FE_API_TOKEN_FILE") or Path.home() / "fiction_engine" / "api_token")
    return path.read_text(encoding="utf-8").strip()


def headers() -> dict:
    return {"X-FE-Token": token()}


class Session(requests.Session):
    """requests.Session с тайм-аутом по умолчанию: post без него ждал вечно."""

    def request(self, *a, **k):
        k.setdefault("timeout", DEFAULT_TIMEOUT)
        return super().request(*a, **k)
