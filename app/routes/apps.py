from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application, BlockedIdentity
from app.routes.templates import TEMPLATES
from app.seed import hostname_from_url, slugify, validate_app_url

router = APIRouter()


def _app_or_404(db: Session, app_id: UUID) -> Application:
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


def _unique_slug(db: Session, name: str, exclude_id: UUID | None = None) -> str:
    base = slugify(name)
    slug = base
    n = 2
    while True:
        existing = db.scalar(select(Application).where(Application.slug == slug))
        if existing is None or existing.id == exclude_id:
            return slug
        slug = f"{base}-{n}"
        n += 1


def _block(db: Session, app: Application) -> None:
    """Hiding an auto-added app block-lists its ingress so discovery skips it."""
    existing = db.scalar(
        select(BlockedIdentity).where(
            (BlockedIdentity.cluster_uid == app.cluster_uid)
            | (
                (BlockedIdentity.namespace == app.namespace)
                & (BlockedIdentity.k8s_name == app.k8s_name)
            )
        ).limit(1)
    )
    if existing is None:
        db.add(
            BlockedIdentity(
                cluster_uid=app.cluster_uid,
                namespace=app.namespace,
                k8s_name=app.k8s_name,
                hostname=app.hostname,
                reason="hidden from dashboard",
            )
        )


def _unblock(db: Session, app: Application) -> None:
    conds = []
    if app.cluster_uid:
        conds.append(BlockedIdentity.cluster_uid == app.cluster_uid)
    if app.namespace and app.k8s_name:
        conds.append(
            (BlockedIdentity.namespace == app.namespace)
            & (BlockedIdentity.k8s_name == app.k8s_name)
        )
    for cond in conds:
        for row in db.scalars(select(BlockedIdentity).where(cond)).all():
            db.delete(row)


@router.get("/apps/new")
def new_app(request: Request):
    return TEMPLATES.TemplateResponse(
        request,
        "app_form.html",
        {"app": None, "error": None, "title": "Add application"},
    )


@router.post("/apps")
def create_app(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    url: str = Form(...),
    description: str = Form(""),
    icon_url: str = Form(""),
    sort_order: int = Form(100),
    open_in_new_tab: bool = Form(False),
):
    try:
        url = validate_app_url(url)
    except ValueError as exc:
        return TEMPLATES.TemplateResponse(
            request,
            "app_form.html",
            {
                "app": None,
                "error": str(exc),
                "title": "Add application",
                "form": {
                    "name": name,
                    "url": url,
                    "description": description,
                    "icon_url": icon_url,
                    "sort_order": sort_order,
                    "open_in_new_tab": open_in_new_tab,
                },
            },
            status_code=400,
        )
    app = Application(
        slug=_unique_slug(db, name),
        name=name.strip(),
        url=url,
        description=description.strip() or None,
        icon_url=icon_url.strip() or None,
        source="manual",
        hostname=hostname_from_url(url),
        hidden=False,
        sort_order=sort_order,
        open_in_new_tab=open_in_new_tab,
    )
    db.add(app)
    db.flush()
    return RedirectResponse("/?flash=added", status_code=303)


@router.get("/apps/{app_id}/edit")
def edit_app(request: Request, app_id: UUID, db: Session = Depends(get_db)):
    app = _app_or_404(db, app_id)
    return TEMPLATES.TemplateResponse(
        request,
        "app_form.html",
        {"app": app, "error": None, "title": f"Edit {app.name}"},
    )


@router.post("/apps/{app_id}")
def update_app(
    request: Request,
    app_id: UUID,
    db: Session = Depends(get_db),
    name: str = Form(...),
    url: str = Form(...),
    description: str = Form(""),
    icon_url: str = Form(""),
    sort_order: int = Form(100),
    open_in_new_tab: bool = Form(False),
):
    app = _app_or_404(db, app_id)
    try:
        url = validate_app_url(url)
    except ValueError as exc:
        return TEMPLATES.TemplateResponse(
            request,
            "app_form.html",
            {"app": app, "error": str(exc), "title": f"Edit {app.name}"},
            status_code=400,
        )
    app.name = name.strip()
    app.url = url
    app.description = description.strip() or None
    app.icon_url = icon_url.strip() or None
    app.hostname = hostname_from_url(url)
    app.sort_order = sort_order
    app.open_in_new_tab = open_in_new_tab
    return RedirectResponse("/?flash=saved", status_code=303)


@router.post("/apps/{app_id}/hide")
def hide_app(app_id: UUID, db: Session = Depends(get_db)):
    app = _app_or_404(db, app_id)
    app.hidden = True
    if app.source == "ingress" and app.namespace and app.k8s_name:
        _block(db, app)
    return RedirectResponse("/settings?flash=hidden", status_code=303)


@router.post("/apps/{app_id}/unhide")
def unhide_app(app_id: UUID, db: Session = Depends(get_db)):
    app = _app_or_404(db, app_id)
    app.hidden = False
    _unblock(db, app)
    return RedirectResponse("/settings?flash=shown", status_code=303)


@router.post("/apps/{app_id}/delete")
def delete_app(app_id: UUID, db: Session = Depends(get_db)):
    app = _app_or_404(db, app_id)
    db.delete(app)
    return RedirectResponse("/?flash=deleted", status_code=303)
