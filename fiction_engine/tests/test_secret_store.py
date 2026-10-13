"""
API-ключи в БД не открытым текстом (ROADMAP, этап 5.2).
"""
import os
import stat


def _raw_rows():
    from engine.db_core import get_conn
    with get_conn() as conn:
        return {r["provider"]: r["api_key"] for r in conn.execute("SELECT provider, api_key FROM api_keys")}


def test_saved_key_is_not_readable_in_db():
    from engine.db_settings import get_api_key, save_api_key
    save_api_key("nano_gpt", "sk-nano-1234567890abcdef")
    raw = _raw_rows()["nano_gpt"]
    assert raw.startswith("enc1:") and "sk-" not in raw and "1234567890" not in raw
    assert get_api_key("nano_gpt") == "sk-nano-1234567890abcdef"


def test_plaintext_keys_are_encrypted_on_init():
    from engine.db_core import get_conn, init_db
    from engine.db_settings import get_api_key
    with get_conn() as conn:
        conn.execute("INSERT INTO api_keys (provider, api_key) VALUES ('openai_direct', 'sk-old-plain-key-0000')")
    assert get_api_key("openai_direct") == "sk-old-plain-key-0000"     # старое читается
    init_db()
    assert _raw_rows()["openai_direct"].startswith("enc1:")
    assert get_api_key("openai_direct") == "sk-old-plain-key-0000"


def test_key_file_created_private(tmp_path, monkeypatch):
    from engine import secret_store
    monkeypatch.setenv("FE_SECRET_KEY_FILE", str(tmp_path / "k" / "secret.key"))
    assert secret_store.decrypt(secret_store.encrypt("секрет")) == "секрет"
    mode = stat.S_IMODE(os.stat(tmp_path / "k" / "secret.key").st_mode)
    assert mode == 0o600


def test_wrong_key_file_gives_none_not_garbage(tmp_path, monkeypatch):
    from engine.db_settings import get_api_key, save_api_key
    save_api_key("deepseek_direct", "sk-deep-abcdef123456")
    monkeypatch.setenv("FE_SECRET_KEY_FILE", str(tmp_path / "other.key"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert get_api_key("deepseek_direct") is None


def test_masked_listing_uses_plain_keys():
    from engine.db_settings import get_all_api_keys, save_api_key
    save_api_key("nano_gpt", "sk-nano-1234567890abcdef")
    assert get_all_api_keys() == {"nano_gpt": "sk-nano-...cdef"}


def test_env_key_overrides_file(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from engine import secret_store
    monkeypatch.setenv("FE_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("FE_SECRET_KEY_FILE", str(tmp_path / "none.key"))
    assert secret_store.decrypt(secret_store.encrypt("x-key")) == "x-key"
    assert not (tmp_path / "none.key").exists()
