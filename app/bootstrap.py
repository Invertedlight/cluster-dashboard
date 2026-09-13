import logging

from alembic.config import Config
from alembic import command

from app.config import get_settings
from app.db import get_session_factory
from app.seed import seed_apps

log = logging.getLogger(__name__)


def run_migrations() -> None:
    cfg = Config("alembic.ini")
    # Use the raw DSN. str(engine.url) hides the password as "***".
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")


def bootstrap() -> None:
    log.info("running database migrations")
    run_migrations()
    db = get_session_factory()()
    try:
        seed_apps(db)
        log.info("seed complete")
    finally:
        db.close()
