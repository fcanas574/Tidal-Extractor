"""Tests for the fast preview stream and metadata routes.

The stream endpoint mirrors the URL resolution of the legacy combined
`GET /preview/{track_id}` route (auth -> track -> LOW-quality url) but returns
immediately with `track_id`, `stream_url`, `duration` -- it must NOT run
waveform or key detection. The metadata endpoint resolves the same url and hands
it off to the module-level `PreviewJobManager`, returning the initial snapshot
without waiting for the background analyzer.
"""
import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.analysis.types import (
    AnalysisSettings,
    GridResult,
    HybridAnalysisResult,
    KeyResult,
    RhythmResult,
)


client = TestClient(main.app)
TEST_TRACK_ID = 123
TEST_STREAM_URL = "https://example.test/full-track"
TEST_DURATION = 240.0


def _analysis_result(*, duration: float = TEST_DURATION, key: str | None = "C",
                     camelot: str | None = "8B", bpm: float | None = 128.0):
    settings = AnalysisSettings()
    return HybridAnalysisResult(
        schema_version=settings.schema_version,
        audio_fingerprint="a" * 64,
        decoder_version=main.DECODER_VERSION,
        duration_seconds=duration,
        model_id=settings.model_id,
        model_sha256="0" * 64,
        key_profile_id=settings.key_profile_id,
        settings_sha256=settings.sha256,
        key=KeyResult(
            key=key,
            camelot=camelot,
            status="reliable" if key is not None else "unknown",
            candidates=(),
            agreement=None,
            reason=None,
        ),
        rhythm=RhythmResult(
            bpm=bpm,
            beats=(),
            downbeats=(),
            grid=GridResult(
                bpm=bpm,
                period_seconds=60.0 / bpm if bpm is not None else None,
                origin_seconds=0.0 if bpm is not None else None,
                meter="4/4" if bpm is not None else None,
                first_downbeat_beat=0 if bpm is not None else None,
                status="reliable" if bpm is not None else "unavailable",
                residual_p95_seconds=0.01 if bpm is not None else None,
                split_drift_seconds=0.0 if bpm is not None else None,
                reason=None,
            ),
            status="reliable" if bpm is not None else "unavailable",
            reason=None,
        ),
    )


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
    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("must not run")
    monkeypatch.setattr(main, "analyze_stream", _must_not_run)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("route", [main.preview_stream, main.preview_metadata])
async def test_preview_routes_resolve_tidal_io_off_event_loop(stub_auth, route, monkeypatch):
    event_loop_thread = threading.get_ident()
    call_threads = []

    class Track(_FakeTrack):
        def get_url(self):
            call_threads.append(threading.get_ident())
            return TEST_STREAM_URL

    def get_track(_track_id):
        call_threads.append(threading.get_ident())
        return Track()

    monkeypatch.setattr(stub_auth, "track", get_track)

    await route(TEST_TRACK_ID)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert call_threads
    assert all(thread_id != event_loop_thread for thread_id in call_threads)


def test_metadata_route_returns_processing_snapshot(stub_auth, monkeypatch):
    """The metadata endpoint resolves the same url, hands it to the preview
    job manager, and returns the initial snapshot -- queued/processing/complete
    depending on scheduling."""
    from backend.preview_jobs import PreviewMetadataSnapshot

    class SnapshotManager:
        def snapshot(self, _track_id):
            return None

        def start_or_get(self, track_id, _stream_url, _duration):
            return PreviewMetadataSnapshot(track_id=track_id, status="queued", revision=1)

    monkeypatch.setattr(main, "preview_job_manager", SnapshotManager())
    response = client.get(f"/preview/{TEST_TRACK_ID}/metadata")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["track_id"] == TEST_TRACK_ID
    assert payload["status"] in {"queued", "processing", "complete"}
    assert set(payload) == {
        "track_id", "status", "revision", "waveform", "key", "camelot", "bpm", "error",
        "waveform_status", "analysis_status", "analysis", "analysis_error",
        "key_source", "bpm_source", "provider_key", "provider_camelot", "provider_bpm",
    }


def test_legacy_preview_route_keeps_display_fields_additive(stub_auth, monkeypatch):
    track = type("Track", (), {
        "title": "Test",
        "artist": type("Artist", (), {"name": "Test Artist"})(),
        "duration": TEST_DURATION,
    })()
    monkeypatch.setattr(main, "_resolve_preview_track", lambda _track_id: (track, TEST_STREAM_URL))

    async def preview_result(*_args, **_kwargs):
        return {
            "waveform": {"bands": {"low": [0.1], "mid": [0.2], "high": [0.3]},
                         "duration": TEST_DURATION},
            "analysis": {
                "key": {"key": "G", "camelot": "9B"},
                "rhythm": {"grid": {"bpm": None}},
            },
            "provider_key": "A",
            "provider_camelot": "8A",
            "provider_bpm": 111.0,
        }

    monkeypatch.setattr(main, "preview_analyzer", preview_result)
    response = client.get(f"/preview/{TEST_TRACK_ID}")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["stream_url"] == TEST_STREAM_URL
    assert payload["key"] == "G"
    assert payload["camelot"] == "9B"
    assert payload["bpm"] == 111.0
    assert payload["key_source"] == "local"
    assert payload["bpm_source"] == "provider"


# ---------------------------------------------------------------------------
# Integration tests for the streaming pipeline (Stage 2, Task 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_analyzer_calls_analyze_stream(monkeypatch):
    """Preview analysis decodes once, then sends the PCM identity to the service."""
    calls: list[str] = []
    wav_path = "/tmp/test_preview_track.wav"

    async def _fake_analyze_stream(
        stream_url, duration=None, width=600, on_snapshot=None,
    ):
        calls.append(stream_url)
        assert width == 600
        return {
            "bands": {"low": [0.1, 0.2], "mid": [0.3, 0.4], "high": [0.5, 0.6]},
            "duration": 240.0,
            "temp_wav_path": wav_path,
            "pcm_sha256": "a" * 64,
        }

    monkeypatch.setattr(main, "analyze_stream", _fake_analyze_stream)
    service = MagicMock()
    service.analyze_preview = AsyncMock(return_value=_analysis_result())
    monkeypatch.setattr(main, "_get_analysis_service", lambda: service)
    monkeypatch.setattr(main, "_freqblog_lookup", AsyncMock(return_value={
        "key": "A", "camelot": "8A", "bpm": 111.0,
    }))
    monkeypatch.setattr(
        main.auth_manager,
        "session",
        type("_", (), {"track": lambda _self, _tid: type("_", (), {
            "title": "Test", "artist": type("_", (), {"name": "Test Artist"})(),
        })()})(),
    )

    result = await main.preview_analyzer(
        TEST_STREAM_URL, TEST_DURATION, TEST_TRACK_ID, on_snapshot=None,
    )

    assert calls == [TEST_STREAM_URL]
    assert result["waveform"]["bands"] == {"low": [0.1, 0.2], "mid": [0.3, 0.4], "high": [0.5, 0.6]}
    assert result["waveform"]["duration"] == 240.0
    assert result["analysis"]["key"]["key"] == "C"
    assert result["provider_key"] == "A"
    assert result["provider_bpm"] == 111.0
    service.analyze_preview.assert_awaited_once()
    analysis_kwargs = service.analyze_preview.await_args.kwargs
    assert str(analysis_kwargs["wav_path"]) == wav_path
    assert analysis_kwargs["pcm_sha256"] == "a" * 64
    assert analysis_kwargs["preview_profile"] == "LOW"
    assert analysis_kwargs["duration_seconds"] == 240.0
    assert analysis_kwargs["decoder_version"] == main.DECODER_VERSION
    display = main.metadata_display_fields(
        result["analysis"], provider_key=result["provider_key"],
        provider_camelot=result["provider_camelot"], provider_bpm=result["provider_bpm"],
    )
    assert display["key"] == "C"
    assert display["camelot"] == "8B"
    assert display["bpm"] == 128.0


@pytest.mark.asyncio
async def test_preview_analyzer_reuses_temp_wav_for_hybrid_service(monkeypatch):
    """The temp WAV from the single decode is handed directly to the service."""
    wav_path = "/tmp/test_preview_track.wav"

    async def _fake_analyze_stream(*_a, **_kw):
        return {
            "bands": {"low": [0.1], "mid": [0.1], "high": [0.1]},
            "duration": 10.0,
            "temp_wav_path": wav_path,
            "pcm_sha256": "b" * 64,
        }

    monkeypatch.setattr(main, "analyze_stream", _fake_analyze_stream)
    service = MagicMock()
    service.analyze_preview = AsyncMock(return_value=_analysis_result(duration=10.0))
    monkeypatch.setattr(main, "_get_analysis_service", lambda: service)
    monkeypatch.setattr(main, "_preview_provider_metadata", AsyncMock(return_value={
        "provider_key": None, "provider_camelot": None, "provider_bpm": None,
    }))

    await main.preview_analyzer(
        TEST_STREAM_URL, TEST_DURATION, TEST_TRACK_ID, on_snapshot=None,
    )

    assert str(service.analyze_preview.await_args.kwargs["wav_path"]) == wav_path
    assert service.analyze_preview.await_args.kwargs["pcm_sha256"] == "b" * 64


@pytest.mark.asyncio
async def test_preview_analyzer_cleans_up_temp_wav(monkeypatch, tmp_path):
    """The decoded WAV stays alive through the worker call, then is deleted."""
    wav = tmp_path / "preview.wav"
    wav.write_bytes(b"RIFF....WAVE....")

    async def _fake_analyze_stream(*_a, **_kw):
        return {
            "bands": {"low": [0.1], "mid": [0.1], "high": [0.1]},
            "duration": 10.0,
            "temp_wav_path": str(wav),
            "pcm_sha256": "c" * 64,
        }

    monkeypatch.setattr(main, "analyze_stream", _fake_analyze_stream)
    service = MagicMock()

    async def analyze_preview(**_kwargs):
        assert wav.exists(), "temp WAV must remain available while worker analysis runs"
        return _analysis_result(duration=10.0)

    service.analyze_preview = analyze_preview
    monkeypatch.setattr(main, "_get_analysis_service", lambda: service)
    monkeypatch.setattr(main, "_preview_provider_metadata", AsyncMock(return_value={
        "provider_key": None, "provider_camelot": None, "provider_bpm": None,
    }))

    await main.preview_analyzer(
        TEST_STREAM_URL, TEST_DURATION, TEST_TRACK_ID, on_snapshot=None,
    )

    assert not wav.exists(), "temp WAV should be cleaned up after worker analysis"


def test_retry_requires_auth_and_never_accepts_path(stub_auth, monkeypatch):
    monkeypatch.setattr(type(main.auth_manager), "is_authenticated", False)
    response = client.post(
        f"/preview/{TEST_TRACK_ID}/analysis/retry",
        json={"path": "/tmp/attacker-controlled.wav"},
    )
    assert response.status_code == 401

    monkeypatch.setattr(type(main.auth_manager), "is_authenticated", True)
    response = client.post(
        f"/preview/{TEST_TRACK_ID}/analysis/retry",
        json={"path": "/tmp/attacker-controlled.wav"},
    )
    assert response.status_code == 422


def test_retry_returns_current_snapshot_without_a_body(stub_auth, monkeypatch):
    from backend.preview_jobs import PreviewMetadataSnapshot

    current = PreviewMetadataSnapshot(
        track_id=TEST_TRACK_ID,
        status="processing",
        revision=5,
        waveform_status="complete",
        analysis_status="queued",
    )

    class RetryManager:
        def snapshot(self, track_id):
            assert track_id == TEST_TRACK_ID
            return current

        def retry_analysis(self, track_id):
            assert track_id == TEST_TRACK_ID
            return current

    monkeypatch.setattr(main, "preview_job_manager", RetryManager())
    response = client.post(f"/preview/{TEST_TRACK_ID}/analysis/retry")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["track_id"] == TEST_TRACK_ID
    assert payload["revision"] == 5
    assert payload["waveform_status"] == "complete"
    assert payload["analysis_status"] == "queued"


@pytest.mark.asyncio
async def test_retry_does_not_restart_on_poll(stub_auth, monkeypatch):
    calls = 0

    async def analyzer(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return {"analysis_status": "failed", "analysis_error": "model unavailable"}

    manager = main.PreviewJobManager(analyzer=analyzer)
    monkeypatch.setattr(main, "preview_job_manager", manager)

    first = await main.preview_metadata(TEST_TRACK_ID)
    assert first["track_id"] == TEST_TRACK_ID
    await asyncio.sleep(0)
    for _ in range(4):
        response = await main.preview_metadata(TEST_TRACK_ID)
        assert response["track_id"] == TEST_TRACK_ID
        await asyncio.sleep(0)

    assert calls == 1


def test_scheduling_error_is_not_mapped_to_not_found(stub_auth, monkeypatch):
    class SchedulingFailure:
        def snapshot(self, _track_id):
            return None

        def start_or_get(self, *_args):
            raise RuntimeError("preview scheduler stopped")

    monkeypatch.setattr(main, "preview_job_manager", SchedulingFailure())
    response = client.get(f"/preview/{TEST_TRACK_ID}/metadata")

    assert response.status_code in {500, 503}
