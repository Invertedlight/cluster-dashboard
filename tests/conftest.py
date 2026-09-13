import os
import time
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
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                response = test_client.get("/")
            except Exception:
                time.sleep(0.05)
                continue
            if response.status_code == 200 and "Linkding" in response.text:
                break
            time.sleep(0.05)
        yield test_client
    reset_engine()
    get_settings.cache_clear()
