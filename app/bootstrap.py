from alembic.config import Config
from alembic import command

from app.db import get_engine, get_session_factory
from app.seed import seed_apps


def run_migrations() -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", str(get_engine().url))
    command.upgrade(cfg, "head")


def bootstrap() -> None:
    run_migrations()
    db = get_session_factory()()
    try:
        seed_apps(db)
    finally:
        db.close()
