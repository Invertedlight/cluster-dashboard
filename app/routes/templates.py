from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

from app.auth import auth_enabled, csrf_token, is_admin  # noqa: E402

TEMPLATES.env.globals.update(is_admin=is_admin, csrf_token=csrf_token, auth_enabled=auth_enabled)
