import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.bootstrap import bootstrap
from app.routes.apps import router as apps_router
from app.routes.health import router as health_router
from app.routes.home import router as home_router
from app.routes.settings import router as settings_router

log = logging.getLogger("uvicorn.error")


async def _run_bootstrap() -> None:
    log.info("database bootstrap starting")
    try:
        await asyncio.to_thread(bootstrap)
        log.info("database bootstrap finished")
    except Exception:
        log.exception("database bootstrap failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_run_bootstrap())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="Homelab dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(health_router)
app.include_router(home_router)
app.include_router(apps_router)
app.include_router(settings_router)
