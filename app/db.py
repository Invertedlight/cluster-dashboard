from collections.abc import Generator
from urllib.parse import urlparse, urlunparse

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def qualify_database_url(url: str) -> str:
    """Treat in-cluster hosts as FQDNs so ndots search domains are not appended.

    Names with fewer dots than ndots (often 5 in this cluster) are rewritten
    as `<name>.jameshomelab.org` and resolve to Cloudflare instead of ClusterIP.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host or host.endswith(".") or not host.endswith(".svc.cluster.local"):
        return url
    userinfo = ""
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse(parsed._replace(netloc=f"{userinfo}{host}.{port}"))


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = qualify_database_url(get_settings().database_url)
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("postgresql"):
            kwargs["connect_args"] = {"connect_timeout": 10}
        _engine = create_engine(url, **kwargs)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reset_engine() -> None:
    """Used by tests to swap DATABASE_URL."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    get_settings.cache_clear()
