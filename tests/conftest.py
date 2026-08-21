from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

IST = ZoneInfo("Asia/Kolkata")
FIXED_NOW = datetime(2026, 8, 21, 12, 0, tzinfo=IST)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixed_clock() -> Callable[[], datetime]:
    return lambda: FIXED_NOW


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        ai_provider="demo",
        fallback_to_demo=True,
        session_ttl_minutes=60,
        max_sessions=100,
        max_messages_per_session=40,
        rate_limit_requests=500,
        rate_limit_window_seconds=60,
        allowed_origins=("http://testserver",),
        allowed_hosts=("testserver", "localhost", "127.0.0.1"),
        project_root=PROJECT_ROOT,
    )


@pytest.fixture
def client(settings: Settings, fixed_clock: Callable[[], datetime]) -> Iterator[TestClient]:
    app = create_app(settings, clock=fixed_clock)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session_id(client: TestClient) -> str:
    response = client.post("/api/sessions", json={"channel": "chat"})
    assert response.status_code == 201
    return response.json()["session_id"]


def send(client: TestClient, session_id: str, message: str, channel: str = "chat") -> dict:
    response = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": message, "channel": channel},
    )
    assert response.status_code == 200, response.text
    return response.json()
