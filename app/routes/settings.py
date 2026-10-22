from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import Application
from app.routes.templates import TEMPLATES

router = APIRouter()

FLASH = {
    "hidden": "Application hidden.",
    "shown": "Application is visible again.",
}


@router.get("/settings", dependencies=[Depends(require_admin)])
def settings(request: Request, db: Session = Depends(get_db)):
    hidden = db.scalars(
        select(Application).where(Application.hidden.is_(True)).order_by(Application.name)
    ).all()
    key = request.query_params.get("flash")
    return TEMPLATES.TemplateResponse(
        request,
        "settings.html",
        {"hidden_apps": hidden, "flash": FLASH.get(key, key)},
    )
