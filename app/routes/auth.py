from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import (
    LIMITER, TOTP, auth_enabled, check_csrf, check_password, client_ip,
    is_admin, login_session, safe_next,
)
from app.routes.templates import TEMPLATES
import logging

log = logging.getLogger("uvicorn.error")
router = APIRouter()


def _page(request: Request, nxt: str, error: str | None = None, status: int = 200):
    return TEMPLATES.TemplateResponse(
        request, "login.html",
        {"next": nxt, "error": error, "enabled": auth_enabled()},
        status_code=status,
    )


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    nxt = safe_next(next)
    if is_admin(request):
        return RedirectResponse(nxt, status_code=303)
    return _page(request, nxt)


@router.post("/login", dependencies=[Depends(check_csrf)])
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    code: str = Form(""),
    next: str = Form("/"),
):
    nxt = safe_next(next)
    if not auth_enabled():
        return _page(request, nxt, "Editing is disabled: the login is not configured.", 503)
    ip = client_ip(request)
    if LIMITER.locked(ip):
        return _page(request, nxt, "Too many failed attempts. Try again in 15 minutes.", 429)
    pw_ok = check_password(username, password)
    # Only consume a TOTP step when the password was right.
    if not (pw_ok and TOTP.verify(code)):
        LIMITER.fail(ip)
        log.info("edit login failed from %s", ip)
        return _page(request, nxt, "Wrong username, password or code.", 401)
    LIMITER.success(ip)
    login_session(request)
    log.info("edit login succeeded from %s", ip)
    return RedirectResponse(nxt, status_code=303)


@router.post("/logout", dependencies=[Depends(check_csrf)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/?flash=signed-out", status_code=303)
