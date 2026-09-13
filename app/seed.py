from __future__ import annotations

import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Application

_SLUG_RE = re.compile(r"[^a-z0-9]+")

SEED_APPS = (
    {
        "slug": "linkding",
        "name": "Linkding",
        "url": "https://lds.jameshomelab.org",
        "description": "Bookmark manager",
        "sort_order": 10,
    },
    {
        "slug": "mealie",
        "name": "Mealie",
        "url": "https://mealie.jameshomelab.org",
        "description": "Recipes and meal planning",
        "sort_order": 20,
    },
    {
        "slug": "audiobookshelf",
        "name": "Audiobookshelf",
        "url": "https://abs.jameshomelab.org",
        "description": "Audiobooks and podcasts",
        "sort_order": 30,
    },
    {
        "slug": "grafana",
        "name": "Grafana",
        "url": "https://grs.jameshomelab.org",
        "description": "Cluster metrics and dashboards",
        "sort_order": 40,
    },
)


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "app"


def hostname_from_url(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def validate_app_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("URL must be https://…")
    host = (parsed.hostname or "").lower()
    domain = get_settings().base_domain.lower()
    if host != domain and not host.endswith("." + domain):
        raise ValueError(f"URL host must be under {domain}")
    return url.strip().rstrip("/")


def seed_apps(db: Session) -> None:
    for item in SEED_APPS:
        existing = db.scalar(select(Application).where(Application.slug == item["slug"]))
        if existing is not None:
            continue
        db.add(
            Application(
                slug=item["slug"],
                name=item["name"],
                url=item["url"],
                description=item["description"],
                source="manual",
                hostname=hostname_from_url(item["url"]),
                hidden=False,
                sort_order=item["sort_order"],
                open_in_new_tab=True,
            )
        )
    db.commit()
