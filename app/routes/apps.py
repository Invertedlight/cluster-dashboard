from uuid import UUID

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.icons import MAX_ICON_BYTES, IconError, fetch_icon, validate_icon
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
    name_locked: bool = Form(False),
    description_locked: bool = Form(False),
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
                    "name_locked": name_locked,
                    "description_locked": description_locked,
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
        name_locked=name_locked,
        description_locked=description_locked,
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
        {"app": app, "error": None, "title": f"Edit {app.name}",
         "flash": ICON_FLASH.get(request.query_params.get("flash", ""))},
    )


ICON_FLASH = {
    "icon-saved": "Local icon copy saved.",
    "icon-removed": "Local icon copy removed.",
}


def _icon_error(request: Request, app: Application, message: str):
    return TEMPLATES.TemplateResponse(
        request,
        "app_form.html",
        {"app": app, "error": message, "title": f"Edit {app.name}"},
        status_code=400,
    )


def _store_icon(app: Application, data: bytes, mime: str) -> None:
    app.icon_data = data
    app.icon_mime = mime
    app.icon_updated_at = datetime.now(timezone.utc)


@router.post("/apps/{app_id}/icon/fetch")
def fetch_app_icon(
    request: Request,
    app_id: UUID,
    db: Session = Depends(get_db),
    icon_url: str = Form(""),
):
    """'Save a local copy': download the Icon URL into the database."""
    app = _app_or_404(db, app_id)
    url = icon_url.strip() or (app.icon_url or "")
    try:
        data, mime = fetch_icon(url)
    except IconError as exc:
        return _icon_error(request, app, f"Couldn't save a local copy: {exc}")
    app.icon_url = url
    _store_icon(app, data, mime)
    return RedirectResponse(f"/apps/{app.id}/edit?flash=icon-saved", status_code=303)


@router.post("/apps/{app_id}/icon/upload")
async def upload_app_icon(
    request: Request,
    app_id: UUID,
    db: Session = Depends(get_db),
    icon_file: UploadFile = File(...),
):
    app = _app_or_404(db, app_id)
    data = await icon_file.read(MAX_ICON_BYTES + 1)
    try:
        if not icon_file.filename:
            raise IconError("Choose an image file to upload.")
        mime = validate_icon(data, icon_file.content_type)
    except IconError as exc:
        return _icon_error(request, app, f"Couldn't use that file: {exc}")
    _store_icon(app, data, mime)
    return RedirectResponse(f"/apps/{app.id}/edit?flash=icon-saved", status_code=303)


@router.post("/apps/{app_id}/icon/remove")
def remove_app_icon(app_id: UUID, db: Session = Depends(get_db)):
    app = _app_or_404(db, app_id)
    app.icon_data = None
    app.icon_mime = None
    app.icon_updated_at = None
    return RedirectResponse(f"/apps/{app.id}/edit?flash=icon-removed", status_code=303)


@router.get("/icons/{slug}")
def serve_icon(request: Request, slug: str, db: Session = Depends(get_db)):
    app = db.scalar(select(Application).where(Application.slug == slug))
    if app is None or not app.has_local_icon or app.icon_data is None:
        raise HTTPException(status_code=404, detail="No local icon")
    etag = f'"{app.slug}-{app.icon_version}"'
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
        # Neutralises scripts in SVGs if one is opened directly.
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=app.icon_data, media_type=app.icon_mime, headers=headers)


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
    name_locked: bool = Form(False),
    description_locked: bool = Form(False),
):
    app = _app_or_404(db, app_id)
    try:
        url = validate_app_url(url)
    except ValueError as exc:
        return TEMPLATES.TemplateResponse(
            request,
            "app_form.html",
            {
                "app": app,
                "error": str(exc),
                "title": f"Edit {app.name}",
                "form": {
                    "name": name,
                    "url": url,
                    "description": description,
                    "icon_url": icon_url,
                    "sort_order": sort_order,
                    "open_in_new_tab": open_in_new_tab,
                    "name_locked": name_locked,
                    "description_locked": description_locked,
                },
            },
            status_code=400,
        )
    app.name = name.strip()
    app.url = url
    app.description = description.strip() or None
    app.icon_url = icon_url.strip() or None
    app.hostname = hostname_from_url(url)
    app.sort_order = sort_order
    app.open_in_new_tab = open_in_new_tab
    app.name_locked = name_locked
    app.description_locked = description_locked
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
