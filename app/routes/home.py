from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application
from app.routes.templates import TEMPLATES

router = APIRouter()

FLASH = {
    "added": "Application added.",
    "saved": "Application saved.",
    "deleted": "Application deleted.",
    "hidden": "Application hidden.",
    "shown": "Application is visible again.",
    "signed-out": "Signed out.",
}


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    apps = db.scalars(
        select(Application)
        .where(Application.hidden.is_(False))
        .order_by(Application.sort_order, Application.name)
    ).all()
    key = request.query_params.get("flash")
    return TEMPLATES.TemplateResponse(
        request,
        "home.html",
        {"apps": apps, "flash": FLASH.get(key, key)},
    )
