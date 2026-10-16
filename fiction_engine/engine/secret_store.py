"""
secret_store.py — шифрование API-ключей в БД (ROADMAP, этап 5.2).

Ключи провайдеров лежали в SQLite открытым текстом: копия projects.db — это
копия всех ключей. Теперь в БД пишется «enc1:» + токен Fernet (AES-128-CBC
и HMAC-SHA256), а ключ шифрования хранится отдельно от базы:

  - FE_SECRET_KEY — ключ Fernet в переменной окружения (сервер, Docker);
  - иначе файл FE_SECRET_KEY_FILE, по умолчанию ~/fiction_engine/secret.key,
    создаётся при первом запуске с правами 600.

Потеря файла ключа — потеря сохранённых ключей провайдеров: их придётся
ввести заново (сами провайдеры, проекты и главы не пострадают).

Старое значение без префикса читается как есть и шифруется при запуске
(encrypt_plaintext_keys из init_db).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from cryptography.fernet import Fernet

PREFIX = "enc1:"


def key_file() -> Path:
    return Path(os.environ.get("FE_SECRET_KEY_FILE")
                or Path.home() / "fiction_engine" / "secret.key")


def private_file(path: Path, make: Callable[[], bytes]) -> bytes:
    """Содержимое файла; нет файла — создать из make() сразу с правами 600."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Сразу 600 — не «записать, потом сузить»
            fd: int | None = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fd = None       # создал параллельный процесс — читаем его файл
        if fd is not None:
            with os.fdopen(fd, "wb") as f:
                f.write(make())
    # Параллельный процесс мог создать файл и ещё не дописать: пустое чтение
    # давало «Fernet key must be 32 url-safe base64-encoded bytes» (CI, xdist)
    for _ in range(100):
        data = path.read_bytes().strip()
        if data:
            return data
        time.sleep(0.05)
    return data


def _raw_key() -> bytes:
    env = os.environ.get("FE_SECRET_KEY", "").strip()
    if env:
        return env.encode()
    from cryptography.fernet import Fernet
    return private_file(key_file(), Fernet.generate_key)


def _fernet() -> "Fernet":
    from cryptography.fernet import Fernet
    return Fernet(_raw_key())


def encrypt(value: str) -> str:
    if not value or value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    """Расшифровать; значение без префикса — старое, открытым текстом, — как есть."""
    if not value or not value.startswith(PREFIX):
        return value
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        raise ValueError(f"ключ API не расшифровывается: файл ключа {key_file()} "
                         f"не тот, которым шифровали (или задан другой FE_SECRET_KEY) — "
                         f"введите ключ провайдера заново") from None


def session_secret() -> str:
    """Секрет сессий Flask, производный от ключа шифрования, — сессии переживают перезапуск."""
    import hashlib
    import hmac
    return hmac.new(_raw_key(), b"fiction-engine-session", hashlib.sha256).hexdigest()
