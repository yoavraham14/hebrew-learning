"""GET /internal/tasks/* — shared-secret-protected task-trigger endpoints
(Cloud Scheduler calls these, not the frontend). See app/routers/internal.py
and DEPLOY.md.
"""

import pytest

from app.config import get_settings


@pytest.fixture()
def with_task_secret(monkeypatch):
    """Configures a real secret for the duration of one test, then clears
    the settings cache again afterward so other tests aren't affected by a
    lingering monkeypatched env var.
    """
    monkeypatch.setenv("INTERNAL_TASK_SECRET", "test-secret-value")
    get_settings.cache_clear()
    yield "test-secret-value"
    get_settings.cache_clear()


def test_generate_topup_rejects_when_secret_not_configured(client):
    # conftest's test app never sets INTERNAL_TASK_SECRET — fails closed.
    resp = client.post("/internal/tasks/generate-topup", headers={"X-Task-Secret": "anything"})
    assert resp.status_code == 401


def test_generate_topup_rejects_missing_header(client, with_task_secret):
    resp = client.post("/internal/tasks/generate-topup")
    assert resp.status_code == 401


def test_generate_topup_rejects_wrong_secret(client, with_task_secret):
    resp = client.post("/internal/tasks/generate-topup", headers={"X-Task-Secret": "wrong"})
    assert resp.status_code == 401


def test_generate_topup_accepts_correct_secret(client, with_task_secret, monkeypatch):
    # Don't actually hit Gemini — just confirm the auth gate passes and the
    # (mocked) task function gets called.
    calls = []
    monkeypatch.setattr("app.routers.internal.check_and_topup", lambda: calls.append(1))

    resp = client.post("/internal/tasks/generate-topup", headers={"X-Task-Secret": with_task_secret})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert calls == [1]


def test_db_keepalive_rejects_when_secret_not_configured(client):
    resp = client.post("/internal/tasks/db-keepalive", headers={"X-Task-Secret": "anything"})
    assert resp.status_code == 401


def test_db_keepalive_accepts_correct_secret(client, with_task_secret):
    resp = client.post("/internal/tasks/db-keepalive", headers={"X-Task-Secret": with_task_secret})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
