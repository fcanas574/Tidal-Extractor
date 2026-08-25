import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

import backend.main as main


@pytest.fixture
def client(monkeypatch):
    # auth_manager.is_authenticated is a read-only property backed by
    # session.check_login(); stub the whole manager instead.
    fake_auth = MagicMock()
    fake_auth.is_authenticated = True
    fake_auth.session.config.quality = "HIGH"
    monkeypatch.setattr(main, "auth_manager", fake_auth)
    return TestClient(main.app)


def _fake_track(monkeypatch, duration=240.0):
    class T:
        title = "t"; artist = type("A", (), {"name": "a"})()
        def get_url(self): return "https://example.test/full-track"
    T.duration = duration
    main.auth_manager.session.track = lambda _id: T()


def test_stream_route_returns_before_analyzer(client, monkeypatch):
    _fake_track(monkeypatch)
    monkeypatch.setattr(main, "get_waveform_cached",
                        lambda _: (_ for _ in ()).throw(AssertionError("must not run")))
    r = client.get("/preview/123/stream")
    assert r.status_code == 200
    body = r.json()
    assert body["stream_url"] == "https://example.test/full-track"
    assert body["duration"] == 240.0


def test_metadata_route_starts_job_and_returns_snapshot(client):
    import asyncio
    async def fake_analyzer(track_id, url, duration):
        await asyncio.sleep(0.01)
        return {}
    main.preview_job_manager.analyzer = fake_analyzer
    r = client.get("/preview/123/metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["track_id"] == 123
    assert body["status"] in {"queued", "processing", "complete"}
