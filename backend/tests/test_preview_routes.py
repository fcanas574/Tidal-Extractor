"""Tests for the fast preview stream and metadata routes.

The stream endpoint mirrors the URL resolution of the legacy combined
`GET /preview/{track_id}` route (auth -> track -> LOW-quality url) but returns
immediately with `track_id`, `stream_url`, `duration` -- it must NOT run
waveform or key detection. The metadata endpoint resolves the same url and hands
it off to the module-level `PreviewJobManager`, returning the initial snapshot
without waiting for the background analyzer.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import backend.main as main


client = TestClient(main.app)
TEST_TRACK_ID = 123
TEST_STREAM_URL = "https://example.test/full-track"
TEST_DURATION = 240.0


class _FakeConfig:
    """Mimics the Tidal session config -- the route sets quality to "LOW" then
    restores the original value."""

    def __init__(self):
        self.quality = "HIGH"


class _FakeTrack:
    """Minimal track stub: returns a fixed stream url and a duration, and
    exposes a settable config via the session stub."""

    def __init__(self):
        self.duration = TEST_DURATION

    def get_url(self):
        return TEST_STREAM_URL


class _FakeSession:
    """Mimics auth_manager.session: .track(id) returns a track, .config is
    settable so the route's quality toggle/restore works."""

    def __init__(self):
        self.config = _FakeConfig()
        self._track = _FakeTrack()

    def track(self, track_id):
        return self._track


@pytest.fixture
def stub_auth(monkeypatch):
    """Authenticate the route and give it a fake Tidal session.

    `is_authenticated` is a property without a setter, so we replace it at the
    class level with a plain `True` to short-circuit the auth check.
    """
    session = _FakeSession()
    fake_track = _FakeTrack()
    monkeypatch.setattr(type(main.auth_manager), "is_authenticated", True)
    monkeypatch.setattr(main.auth_manager, "session", session)
    monkeypatch.setattr(session, "track", lambda _tid: fake_track)
    # Keep the analyzer a trivial no-op so no real analysis runs.
    async def _noop_analyzer(*_args):
        return {}
    manager = main.PreviewJobManager(analyzer=_noop_analyzer)
    monkeypatch.setattr(main, "preview_job_manager", manager)
    return session


def test_stream_route_returns_before_analyzer(stub_auth, monkeypatch):
    """The stream endpoint returns the resolved url immediately and must not
    invoke waveform generation / key detection."""
    def _must_not_run(_):
        raise AssertionError("must not run")
    monkeypatch.setattr(main, "get_waveform_cached", _must_not_run)
    # Also block key detection in case the stream route ever drifts.
    async def _die_key(*_args, **_kwargs):
        raise AssertionError("must not run")
    monkeypatch.setattr(main, "_detect_preview_key", _die_key)

    response = client.get(f"/preview/{TEST_TRACK_ID}/stream")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["track_id"] == TEST_TRACK_ID
    assert payload["stream_url"] == TEST_STREAM_URL
    assert payload["duration"] == TEST_DURATION
    # The route must restore the original quality.
    assert stub_auth.config.quality == "HIGH"


def test_metadata_route_returns_processing_snapshot(stub_auth):
    """The metadata endpoint resolves the same url, hands it to the preview
    job manager, and returns the initial snapshot -- queued/processing/complete
    depending on scheduling."""
    response = client.get(f"/preview/{TEST_TRACK_ID}/metadata")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["track_id"] == TEST_TRACK_ID
    assert payload["status"] in {"queued", "processing", "complete"}
    assert set(payload) == {"track_id", "status", "revision", "waveform", "key", "camelot", "bpm", "error"}
