import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///" + str(Path("/tmp/cluster-dashboard-test.db"))
os.environ["SECRET_KEY"] = "test"


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'dash.db'}"
    from app.config import get_settings
    from app.db import reset_engine

    get_settings.cache_clear()
    reset_engine()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    reset_engine()
    get_settings.cache_clear()
