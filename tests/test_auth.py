import os
import time

import pyotp
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_TOTP_SECRET, csrf_from, login


def _any_app_id(c):
    from app.db import get_session_factory
    from app.models import Application
    from sqlalchemy import select
    with get_session_factory()() as db:
        return db.scalars(select(Application)).first().id


def test_home_public_without_edit_controls(anon_client):
    r = anon_client.get("/")
    assert r.status_code == 200 and "Linkding" in r.text
    assert "/edit" not in r.text and "/apps/new" not in r.text
    assert "/settings" not in r.text and "/hide" not in r.text and "/delete" not in r.text
    assert "Sign in" in r.text and "Sign out" not in r.text


def test_signed_in_sees_controls(client):
    r = client.get("/")
    assert "/edit" in r.text and "/apps/new" in r.text and "/settings" in r.text
    assert "Sign out" in r.text and ">Sign in<" not in r.text


def test_public_routes_stay_public(anon_client):
    assert anon_client.get("/healthz").status_code == 200
    assert anon_client.get("/readyz").status_code == 200
    assert anon_client.get("/static/style.css").status_code == 200
    assert anon_client.get("/icons/nope").status_code == 404  # not 403/redirect


def test_protected_get_pages_redirect(anon_client):
    app_id = _any_app_id(anon_client)
    for path in ("/apps/new", f"/apps/{app_id}/edit", "/settings"):
        r = anon_client.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert r.headers["location"].startswith("/login?next=%2F")


def test_all_mutations_refused_when_signed_out(anon_client):
    app_id = _any_app_id(anon_client)
    posts = ["/apps", f"/apps/{app_id}", f"/apps/{app_id}/hide", f"/apps/{app_id}/unhide",
             f"/apps/{app_id}/delete", f"/apps/{app_id}/icon/fetch", f"/apps/{app_id}/icon/upload",
             f"/apps/{app_id}/icon/remove"]
    tok = csrf_from(anon_client.get("/login").text)
    for p in posts:
        r = anon_client.post(p, data={"csrf_token": tok, "name": "x", "url": "https://x.jameshomelab.org"},
                             follow_redirects=False)
        assert r.status_code == 403, p
    assert _any_app_id(anon_client)  # nothing deleted


def test_csrf_required_when_signed_in(client):
    app_id = _any_app_id(client)
    good = client.headers.pop("X-CSRF-Token")
    assert client.post(f"/apps/{app_id}/hide", follow_redirects=False).status_code == 403
    assert client.post(f"/apps/{app_id}/hide", data={"csrf_token": "wrong"},
                       follow_redirects=False).status_code == 403
    assert client.post(f"/apps/{app_id}/hide", data={"csrf_token": good},
                       follow_redirects=False).status_code == 303


def test_login_requires_csrf(anon_client):
    r = anon_client.post("/login", data={"username": "admin", "password": "x", "code": "123456"})
    assert r.status_code == 403


def test_wrong_password_and_wrong_code(anon_client):
    assert login(anon_client, password="nope").status_code == 401
    assert login(anon_client, code="000000" if pyotp.TOTP(TEST_TOTP_SECRET).now() != "000000" else "111111").status_code == 401
    assert login(anon_client, code="abc").status_code == 401
    assert "Sign out" not in anon_client.get("/").text


def test_totp_allows_one_step_drift_but_not_two(anon_client):
    t = pyotp.TOTP(TEST_TOTP_SECRET)
    assert login(anon_client, code=t.at(time.time() - 90)).status_code == 401
    assert login(anon_client, code=t.at(time.time() - 30)).status_code == 303


def test_totp_code_cannot_be_reused(client, tmp_path):
    # The fixture already used the current code; a replay must fail.
    fresh = TestClient(client.app, base_url="https://testserver")
    with fresh:
        r = login(fresh, code=pyotp.TOTP(TEST_TOTP_SECRET).now())
        assert r.status_code == 401


def test_lockout_after_five_failures(anon_client):
    for _ in range(5):
        assert login(anon_client, password="bad").status_code == 401
    assert login(anon_client).status_code == 429  # right password still refused


def test_lockout_is_per_ip_and_trusts_only_proxies(anon_client):
    from app.auth import LIMITER
    from starlette.requests import Request
    from app.auth import client_ip

    def req(peer, headers):
        return Request({"type": "http", "client": (peer, 1), "headers":
                        [(k.lower().encode(), v.encode()) for k, v in headers.items()]})

    assert client_ip(req("10.42.0.7", {"CF-Connecting-IP": "1.2.3.4"})) == "1.2.3.4"
    assert client_ip(req("10.42.0.7", {"X-Forwarded-For": "6.6.6.6, 5.6.7.8"})) == "5.6.7.8"
    assert client_ip(req("192.168.1.50", {"CF-Connecting-IP": "1.2.3.4"})) == "192.168.1.50"
    now = time.time()
    for _ in range(5):
        LIMITER.fail("9.9.9.9", now)
    assert LIMITER.locked("9.9.9.9", now + 60)
    assert not LIMITER.locked("8.8.8.8", now + 60)
    assert not LIMITER.locked("9.9.9.9", now + 15 * 60 + 1)


def test_logout(client):
    tok = client.headers["X-CSRF-Token"]
    r = client.post("/logout", data={"csrf_token": tok}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/settings", follow_redirects=False).status_code == 303
    assert "Sign in" in client.get("/").text


def test_logout_get_not_allowed(client):
    assert client.get("/logout").status_code == 405


def test_next_cannot_redirect_off_site(anon_client):
    r = login(anon_client, next="//evil.example/x")
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_next_local_path_kept(anon_client):
    r = login(anon_client, next="/settings")
    assert r.headers["location"] == "/settings"


def test_session_cookie_flags(anon_client):
    r = login(anon_client)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert "max-age=43200" in cookie


def test_session_expires_after_max_age(client, monkeypatch):
    import app.auth as auth
    real = time.time
    monkeypatch.setattr(auth.time, "time", lambda: real() + 12 * 3600 + 5)
    assert client.get("/settings", follow_redirects=False).status_code == 303


def test_fail_closed_without_auth_env(anon_client, monkeypatch, caplog):
    from app.config import get_settings
    monkeypatch.setenv("TOTP_SECRET", "")
    get_settings.cache_clear()
    try:
        assert not get_settings().auth_configured
        assert anon_client.get("/").status_code == 200
        page = anon_client.get("/login")
        assert "Editing is disabled" in page.text
        assert 'name="password"' not in page.text
        r = anon_client.post("/login", data={"username": "admin", "password": "x", "code": "123456"})
        assert r.status_code in (403, 503)
        assert anon_client.get("/settings", follow_redirects=False).status_code == 303
        import logging
        from app.auth import warn_if_unconfigured
        lg = logging.getLogger("uvicorn.error")
        lg.disabled = False  # alembic fileConfig disables existing loggers in tests
        lg.addHandler(caplog.handler)
        try:
            warn_if_unconfigured()
        finally:
            lg.removeHandler(caplog.handler)
        assert "Editing is disabled" in caplog.text
    finally:
        get_settings.cache_clear()


def test_secrets_not_in_pages_or_logs(client, caplog):
    from tests.conftest import AUTH_ENV, TEST_PASSWORD
    html = client.get("/").text + client.get("/login").text
    for v in (AUTH_ENV["ADMIN_PASSWORD_HASH"], AUTH_ENV["SESSION_SECRET"], TEST_TOTP_SECRET, TEST_PASSWORD):
        assert v not in html and v not in caplog.text
