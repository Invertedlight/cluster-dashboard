import os
import time
from collections.abc import Generator
from pathlib import Path

import re

import bcrypt
import pyotp
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///" + str(Path("/tmp/cluster-dashboard-test.db"))
os.environ["SECRET_KEY"] = "test"
# Test-only credentials, generated fresh for every run (never real values).
TEST_USER = "admin"
TEST_PASSWORD = "test-password-not-real"
# setdefault: conftest may be imported twice (as conftest and tests.conftest).
TEST_TOTP_SECRET = os.environ.setdefault("_TEST_TOTP_SECRET", pyotp.random_base32())
_TEST_HASH = os.environ.setdefault(
    "_TEST_PW_HASH", bcrypt.hashpw(b"test-password-not-real", bcrypt.gensalt(rounds=4)).decode()
)
AUTH_ENV = {
    "ADMIN_USERNAME": TEST_USER,
    "ADMIN_PASSWORD_HASH": _TEST_HASH,
    "SESSION_SECRET": "test-session-secret",
    "TOTP_SECRET": TEST_TOTP_SECRET,
}
os.environ.update(AUTH_ENV)


def csrf_from(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "no csrf token in page"
    return m.group(1)


def login(c: TestClient, code: str | None = None, password: str = TEST_PASSWORD, **extra):
    page = c.get("/login")
    data = {"csrf_token": csrf_from(page.text), "username": TEST_USER, "password": password,
            "code": code if code is not None else pyotp.TOTP(TEST_TOTP_SECRET).now()}
    data.update(extra)
    return c.post("/login", data=data, follow_redirects=False)


@pytest.fixture
def anon_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """A visitor who is not signed in."""
    yield from _make_client(tmp_path)


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Signed-in admin; the CSRF token is sent as a header on every request."""
    for c in _make_client(tmp_path):
        r = login(c)
        assert r.status_code == 303, r.text
        c.headers["X-CSRF-Token"] = csrf_from(c.get("/").text)
        yield c


def _make_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'dash.db'}"
    os.environ.update(AUTH_ENV)
    from app.auth import LIMITER, TOTP

    LIMITER.reset()
    TOTP.reset()
    from app.config import get_settings
    from app.db import reset_engine

    get_settings.cache_clear()
    reset_engine()

    from app.main import app

    with TestClient(app, base_url="https://testserver") as test_client:
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                response = test_client.get("/")
            except Exception:
                time.sleep(0.05)
                continue
            if response.status_code == 200 and "Linkding" in response.text:
                break
            time.sleep(0.05)
        yield test_client
    reset_engine()
    get_settings.cache_clear()
