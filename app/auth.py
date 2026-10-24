"""Single-admin edit login: bcrypt password + TOTP, signed session, CSRF, lockout."""

from __future__ import annotations

import hmac
import ipaddress
import logging
import secrets
import threading
import time
from collections import deque
from urllib.parse import quote

import bcrypt
import pyotp
from fastapi import HTTPException, Request

from app.config import get_settings

log = logging.getLogger("uvicorn.error")

TOTP_STEP = 30
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"
# Used so an unknown username still costs one bcrypt check (no timing hint).
_DUMMY_HASH = bcrypt.hashpw(b"not-the-password", bcrypt.gensalt(rounds=12))


# ---------- configuration ----------

def auth_enabled() -> bool:
    return get_settings().auth_configured


def warn_if_unconfigured() -> None:
    if not auth_enabled():
        log.warning(
            "edit login is NOT configured (ADMIN_USERNAME, ADMIN_PASSWORD_HASH, "
            "SESSION_SECRET and TOTP_SECRET are required). Editing is disabled; "
            "the home page still works."
        )


# ---------- client IP ----------

def _trusted_networks():
    nets = []
    for part in get_settings().trusted_proxies.split(","):
        part = part.strip()
        if part:
            try:
                nets.append(ipaddress.ip_network(part, strict=False))
            except ValueError:
                log.warning("ignoring bad TRUSTED_PROXIES entry %r", part)
    return nets


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_ip in net for net in _trusted_networks()):
        return peer
    cf = request.headers.get("cf-connecting-ip", "").strip()
    if cf:
        return cf
    xff = request.headers.get("x-forwarded-for", "")
    hops = [h.strip() for h in xff.split(",") if h.strip()]
    if hops:
        # Rightmost hop is the one our trusted proxy (Traefik) appended.
        return hops[-1]
    return peer


# ---------- lockout ----------

class LoginLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fails: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()
            self._locked_until.clear()

    def locked(self, ip: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            until = self._locked_until.get(ip)
            if until and until > now:
                return True
            if until:
                self._locked_until.pop(ip, None)
            return False

    def fail(self, ip: str, now: float | None = None) -> None:
        s = get_settings()
        now = time.time() if now is None else now
        with self._lock:
            q = self._fails.setdefault(ip, deque())
            q.append(now)
            while q and q[0] <= now - s.login_window_seconds:
                q.popleft()
            if len(q) >= s.login_max_failures:
                self._locked_until[ip] = now + s.login_lockout_seconds
                q.clear()
                log.warning("edit login: %s locked out for %ss after %s failures",
                            ip, s.login_lockout_seconds, s.login_max_failures)

    def success(self, ip: str) -> None:
        with self._lock:
            self._fails.pop(ip, None)


LIMITER = LoginLimiter()


# ---------- credentials ----------

def check_password(username: str, password: str) -> bool:
    s = get_settings()
    user_ok = hmac.compare_digest(username.encode(), s.admin_username.encode())
    stored = s.admin_password_hash.encode() if user_ok else _DUMMY_HASH
    try:
        pw_ok = bcrypt.checkpw(password.encode(), stored)
    except ValueError:
        log.error("ADMIN_PASSWORD_HASH is not a valid bcrypt hash")
        pw_ok = False
    return user_ok and pw_ok


class TotpGuard:
    """RFC 6238, +/-1 step, and each code (time step) usable only once."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_step = -1

    def reset(self) -> None:
        with self._lock:
            self._last_step = -1

    def verify(self, code: str, now: float | None = None) -> bool:
        code = "".join(code.split())
        if len(code) != 6 or not code.isdigit():
            return False
        now = time.time() if now is None else now
        try:
            totp = pyotp.TOTP(get_settings().totp_secret.strip(), interval=TOTP_STEP)
        except Exception:
            log.error("TOTP_SECRET is not valid base32")
            return False
        current = int(now // TOTP_STEP)
        for step in (current - 1, current, current + 1):
            if hmac.compare_digest(totp.at(step * TOTP_STEP), code):
                with self._lock:
                    if step <= self._last_step:
                        log.warning("edit login: rejected reused TOTP code")
                        return False
                    self._last_step = step
                return True
        return False


TOTP = TotpGuard()


# ---------- session / CSRF ----------

def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        request.session["csrf"] = tok
    return tok


def is_admin(request: Request) -> bool:
    if not auth_enabled():
        return False
    user = request.session.get("user")
    login_at = request.session.get("login_at", 0)
    if not user or not hmac.compare_digest(str(user), get_settings().admin_username):
        return False
    if time.time() - float(login_at) > get_settings().session_max_age:
        request.session.clear()
        return False
    return True


async def check_csrf(request: Request) -> None:
    expected = request.session.get("csrf")
    sent = request.headers.get(CSRF_HEADER, "")
    if not sent:
        form = await request.form()
        sent = str(form.get(CSRF_FIELD, ""))
    if not expected or not sent or not hmac.compare_digest(expected, sent):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")


def login_session(request: Request) -> None:
    request.session.clear()
    request.session["user"] = get_settings().admin_username
    request.session["login_at"] = time.time()
    request.session["csrf"] = secrets.token_urlsafe(32)


def safe_next(target: str | None) -> str:
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


async def require_admin(request: Request) -> None:
    """Guard for edit pages (GET -> redirect to login) and all changes (POST -> 403)."""
    if request.method in ("GET", "HEAD"):
        if not is_admin(request):
            nxt = request.url.path
            if request.url.query:
                nxt += "?" + request.url.query
            raise HTTPException(status_code=303, headers={"Location": "/login?next=" + quote(nxt, safe="")})
        return
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Sign in to make changes")
    await check_csrf(request)
