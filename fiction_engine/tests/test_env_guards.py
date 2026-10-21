"""Среда и безопасность (разбор 21.10, группа 4)."""
import subprocess
import sys
import time

import pytest


def test_foreign_host_is_refused(monkeypatch):
    """DNS rebinding: запрос с чужим именем в Host — отказ, петля — как раньше."""
    from web.app import app
    from web.security import allowed_request_host
    monkeypatch.delenv("FE_TRUSTED_HOSTS", raising=False)
    monkeypatch.delenv("FE_HOST", raising=False)
    c = app.test_client()
    assert c.get("/api/voice/active", headers={"Host": "evil.example:5000"}).status_code == 403
    assert c.get("/api/voice/active", headers={"Host": "127.0.0.1:5000"}).status_code != 403
    assert allowed_request_host("localhost") and allowed_request_host("[::1]:5000")
    monkeypatch.setenv("FE_TRUSTED_HOSTS", "book.lan")
    assert allowed_request_host("book.lan:5000") and not allowed_request_host("evil.example")
    monkeypatch.delenv("FE_TRUSTED_HOSTS")
    monkeypatch.setenv("FE_HOST", "0.0.0.0")            # в сети без списка — не проверяется
    assert allowed_request_host("192.168.1.5:5000")


def test_cli_timeout_kills_whole_tree():
    """Потомок держит трубы — без убийства дерева чтение ждало бы его минуту."""
    from engine.api import run_cli
    child = "import time; time.sleep(60)"
    parent = (f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); "
              "time.sleep(60)")
    t = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_cli([sys.executable, "-c", parent], input="", timeout=2)
    assert time.monotonic() - t < 30
