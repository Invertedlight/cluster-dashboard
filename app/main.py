from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl

from app.config import settings

app = FastAPI(title=settings.title)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


class AppCard(BaseModel):
    name: str
    description: str
    url: HttpUrl
    icon: str = "🔗"


# Placeholder cards — replace with live discovery later
DEFAULT_CARDS = [
    AppCard(
        name="Mealie",
        description="Recipes & meal planning",
        url="https://mealie.jameshomelab.org",
        icon="🍽️",
    ),
    AppCard(
        name="Linkding",
        description="Bookmarks",
        url="https://lds.jameshomelab.org",
        icon="🔖",
    ),
    AppCard(
        name="Audiobookshelf",
        description="Audiobooks & podcasts",
        url="https://abs.jameshomelab.org",
        icon="🎧",
    ),
]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/cards", response_model=list[AppCard])
def list_cards() -> list[AppCard]:
    return DEFAULT_CARDS


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": settings.title,
            "cards": DEFAULT_CARDS,
        },
    )
