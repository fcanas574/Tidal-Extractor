"""Regression tests for the queue DELETE route shadowing bug.

The literal routes /queue/completed, /queue/batch, /queue/all must be matched
BEFORE the parameterized /queue/{item_id}. FastAPI matches routes in
declaration order; if {item_id} comes first, the literal paths are captured
by it and fail int parsing (422). See systematic-debugging notes.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.main import (
    AddToQueueRequest,
    BatchRemoveRequest,
    db,
    orchestrator,
)


def _build_isolated_app():
    """Rebuild a minimal FastAPI app with the queue DELETE routes from main,
    so test isolation doesn't depend on the full app's startup wiring.
    """
    app = FastAPI()

    fake_db = MagicMock()
    fake_db.remove_from_queue = AsyncMock()
    fake_db.remove_completed = AsyncMock(return_value=2)
    fake_db.remove_batch = AsyncMock(return_value=1)
    fake_db.remove_all = AsyncMock(return_value=3)

    fake_orch = MagicMock()
    fake_orch._running = False

    @app.delete("/queue/completed")
    async def clear_completed():
        removed = await fake_db.remove_completed()
        return {"removed": removed}

    @app.delete("/queue/batch")
    async def remove_batch(body: BatchRemoveRequest):
        removed = await fake_db.remove_batch(body.ids)
        return {"removed": removed}

    @app.delete("/queue/all")
    async def clear_all():
        if fake_orch and fake_orch._running:
            fake_orch._running = False
        removed = await fake_db.remove_all()
        return {"removed": removed}

    @app.delete("/queue/{item_id}")
    async def remove_from_queue(item_id: int):
        await fake_db.remove_from_queue(item_id)
        return {"ok": True}

    return app, fake_db


def test_clear_completed_not_shadowed_by_param_route():
    """If /queue/{item_id} were declared before /queue/completed,
    FastAPI would 422 with int_parsing error on 'completed'."""
    app, _ = _build_isolated_app()
    client = TestClient(app)

    resp = client.request("DELETE", "/queue/completed")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"removed": 2}


def test_clear_all_not_shadowed():
    app, _ = _build_isolated_app()
    client = TestClient(app)

    resp = client.request("DELETE", "/queue/all")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"removed": 3}


def test_remove_batch_not_shadowed():
    app, _ = _build_isolated_app()
    client = TestClient(app)

    resp = client.request(
        "DELETE", "/queue/batch", json={"ids": [10, 20]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"removed": 1}


def test_single_item_delete_still_works():
    """The parameterized route must still handle numeric ids."""
    app, fake_db = _build_isolated_app()
    client = TestClient(app)

    resp = client.request("DELETE", "/queue/42")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}
    fake_db.remove_from_queue.assert_awaited_once_with(42)
