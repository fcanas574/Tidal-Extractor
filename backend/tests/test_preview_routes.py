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


# ---------------------------------------------------------------------------
# Integration tests for the streaming pipeline (Stage 2, Task 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_analyzer_calls_analyze_stream(monkeypatch):
    """_preview_analyzer delegates waveform analysis to analyze_stream and
    includes the streamed bands in the return dict alongside key data."""
    calls: list[str] = []

    async def _fake_analyze_stream(
        stream_url, duration=None, width=600, on_snapshot=None,
    ):
        calls.append(stream_url)
        assert width == 600
        return {
            "bands": {"low": [0.1, 0.2], "mid": [0.3, 0.4], "high": [0.5, 0.6]},
            "duration": 240.0,
            "temp_wav_path": None,
        }

    monkeypatch.setattr(main, "analyze_stream", _fake_analyze_stream)

    # Direct attribute assignment instead of monkeypatch.setattr for the analyzer
    # to avoid any module-namespace resolution issues.
    original_detect = main._detect_preview_key

    async def _fake_detect_key(*_a, **_kw):
        return {"key": "C", "camelot": "8B", "bpm": 128.0}

    main._detect_preview_key = _fake_detect_key
    # Stub the session so auth_manager.session.track() returns a dummy track.
    orig_session = main.auth_manager.session
    main.auth_manager.session = type("_", (), {"track": lambda _self, _tid: type("_", (), {"title": "Test", "artist": type("_", (), {"name": "Test Artist"})()})()})()

    try:
        result = await main._preview_analyzer(
            TEST_STREAM_URL, TEST_DURATION, TEST_TRACK_ID, on_snapshot=None,
        )
    finally:
        main._detect_preview_key = original_detect
        main.auth_manager.session = orig_session

    assert calls == [TEST_STREAM_URL]
    assert result["waveform"] == {"low": [0.1, 0.2], "mid": [0.3, 0.4], "high": [0.5, 0.6]}
    assert result["key"] == "C"
    assert result["camelot"] == "8B"
    assert result["bpm"] == 128.0


@pytest.mark.asyncio
async def test_preview_analyzer_reuses_temp_wav_for_key_detection(monkeypatch):
    """When analyze_stream returns a temp_wav_path, _detect_preview_key receives
    it as audio_path, avoiding a second full-track network request."""
    async def _fake_analyze_stream(*_a, **_kw):
        return {
            "bands": {"low": [], "mid": [], "high": []},
            "duration": 10.0,
            "temp_wav_path": "/tmp/test_preview_track.wav",
        }

    monkeypatch.setattr(main, "analyze_stream", _fake_analyze_stream)

    received_audio_path: str | None = None

    async def _fake_detect_key(*_a, audio_path=None, **_kw):
        nonlocal received_audio_path
        received_audio_path = audio_path
        return {"key": None, "camelot": None, "bpm": None}

    monkeypatch.setattr(main, "_detect_preview_key", _fake_detect_key)
    monkeypatch.setattr("os.path.exists", lambda p: True)
    orig_session = main.auth_manager.session
    main.auth_manager.session = type("_", (), {"track": lambda _self, _tid: type("_", (), {"title": "Test", "artist": type("_", (), {"name": "Test Artist"})()})()})()

    await main._preview_analyzer(
        TEST_STREAM_URL, TEST_DURATION, TEST_TRACK_ID, on_snapshot=None,
    )

    assert received_audio_path == "/tmp/test_preview_track.wav"

    main.auth_manager.session = orig_session


@pytest.mark.asyncio
async def test_preview_analyzer_cleans_up_temp_wav(monkeypatch, tmp_path):
    """The temp WAV left by analyze_stream is deleted by _preview_analyzer in its
    finally block after key detection completes."""
    wav = tmp_path / "preview.wav"
    wav.write_bytes(b"RIFF....WAVE....")

    async def _fake_analyze_stream(*_a, **_kw):
        return {
            "bands": {"low": [], "mid": [], "high": []},
            "duration": 10.0,
            "temp_wav_path": str(wav),
        }

    monkeypatch.setattr(main, "analyze_stream", _fake_analyze_stream)
    monkeypatch.setattr(main, "_detect_preview_key",
                        lambda *a, **kw: asyncio.sleep(0) or {"key": None, "camelot": None})
    monkeypatch.setattr(main.auth_manager, "session",
                        type("_", (), {"track": lambda _tid: type("_", (), {})()})())

    await main._preview_analyzer(
        TEST_STREAM_URL, TEST_DURATION, TEST_TRACK_ID, on_snapshot=None,
    )

    assert not wav.exists(), "temp WAV should be cleaned up after key detection"
