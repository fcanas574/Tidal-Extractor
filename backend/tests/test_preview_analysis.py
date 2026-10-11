import threading
from pathlib import Path

import pytest
import backend.main as main


def _install_fake_analysis_service(monkeypatch, observed=None, analysis=None):
    payload = analysis or {
        "key": {"key": "Am", "camelot": "4A", "status": "reliable"},
        "rhythm": {"grid": {"bpm": 128.0, "status": "reliable"}},
    }

    class Service:
        async def analyze_preview(self, **kwargs):
            if observed is not None:
                observed.update(kwargs)
            return object()

    monkeypatch.setattr(main, "_get_analysis_service", lambda: Service())
    monkeypatch.setattr(
        main, "_analysis_lifecycle", lambda _result: ("complete", None, payload)
    )


def _decoded(bands, wav_path, *, duration=12.0, fingerprint="a" * 64):
    return {
        "bands": bands,
        "duration": duration,
        "temp_wav_path": str(wav_path),
        "pcm_sha256": fingerprint,
    }


def _fake_session_track(monkeypatch):
    """auth_manager.session is None until the app lifespan logs in, so install a stub."""
    track = type("T", (), {"title": "t",
                           "artist": type("A", (), {"name": "a"})()})()
    session = type("S", (), {"track": staticmethod(lambda _id: track)})()
    monkeypatch.setattr(main.auth_manager, "session", session)


@pytest.mark.asyncio
async def test_uses_one_stream_and_passes_pcm_identity(monkeypatch, tmp_path):
    calls = []
    observed = {}
    wav = tmp_path / "preview.wav"
    wav.write_bytes(b"wav")
    bands = {"low": [0.1], "mid": [0.2], "high": [0.3]}

    async def fake_analyze(url, duration, **kw):
        calls.append(url)
        return _decoded(bands, wav, duration=240.0)

    async def fake_fb(*a, **k):
        return None

    _install_fake_analysis_service(monkeypatch, observed)
    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    _fake_session_track(monkeypatch)

    result = await main.preview_analyzer(stream_url="https://s/7", duration=240.0, track_id=7)
    assert calls == ["https://s/7"]
    assert observed["track_id"] == 7
    assert observed["pcm_sha256"] == "a" * 64
    assert observed["wav_path"] == Path(wav)
    assert observed["duration_seconds"] == 240.0
    assert result["waveform"]["bands"]["mid"] == [0.2]
    assert not wav.exists()


@pytest.mark.asyncio
async def test_identityless_waveform_cache_is_not_reused(monkeypatch, tmp_path):
    calls = []
    wav = tmp_path / "preview.wav"
    wav.write_bytes(b"wav")
    bands = {"low": [0.4], "mid": [0.5], "high": [0.6]}

    async def fake_analyze(url, duration, **kw):
        calls.append(url)
        return _decoded(bands, wav)

    async def identityless_cache(_):
        return {"bands": {"low": [1.0], "mid": [1.0], "high": [1.0]}, "duration": 12.0}

    async def no_provider(_tid):
        return {"provider_key": None, "provider_camelot": None, "provider_bpm": None}

    _install_fake_analysis_service(monkeypatch)
    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main.db, "get_waveform_cache", identityless_cache)
    monkeypatch.setattr(main, "_preview_provider_metadata", no_provider)
    result = await main.preview_analyzer(stream_url="https://s/9", duration=12.0, track_id=9)
    assert calls == ["https://s/9"]
    assert result["waveform"]["bands"]["high"] == [0.6]


@pytest.mark.asyncio
async def test_empty_waveform_cache_is_redecoded_once(monkeypatch, tmp_path):
    calls = []
    wav = tmp_path / "preview.wav"
    wav.write_bytes(b"wav")
    bands = {"low": [0.1], "mid": [0.2], "high": [0.3]}

    async def empty_cache(_):
        return {"bands": {"low": [], "mid": [], "high": []}, "duration": 12.0}

    async def fake_analyze(url, duration, **kw):
        calls.append(url)
        return _decoded(bands, wav)

    async def fake_fb(*a, **k):
        return None

    _install_fake_analysis_service(monkeypatch)
    monkeypatch.setattr(main.db, "get_waveform_cache", empty_cache)
    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    _fake_session_track(monkeypatch)

    result = await main.preview_analyzer(stream_url="https://s/17", duration=12.0, track_id=17)

    assert calls == ["https://s/17"]
    assert result["waveform"]["bands"]["high"] == [0.3]


@pytest.mark.asyncio
async def test_empty_waveform_is_rejected(monkeypatch, tmp_path):
    wav = tmp_path / "empty.wav"
    wav.write_bytes(b"wav")

    async def empty_analysis(url, duration, **kw):
        return _decoded({"low": [], "mid": [], "high": []}, wav)

    async def no_provider(_tid):
        return {"provider_key": None, "provider_camelot": None, "provider_bpm": None}

    monkeypatch.setattr(main, "_preview_provider_metadata", no_provider)
    monkeypatch.setattr(main, "analyze_stream", empty_analysis)
    _install_fake_analysis_service(monkeypatch)

    with pytest.raises(RuntimeError, match="no samples"):
        await main.preview_analyzer(stream_url="https://s/18", duration=12.0, track_id=18)

    assert not wav.exists()


@pytest.mark.asyncio
async def test_preview_analyzer_resolves_track_off_event_loop(monkeypatch, tmp_path):
    event_loop_thread = threading.get_ident()
    call_threads = []

    class Session:
        def track(self, _track_id):
            call_threads.append(threading.get_ident())
            return type("T", (), {
                "title": "t",
                "artist": type("A", (), {"name": "a"})(),
            })()

    wav = tmp_path / "preview.wav"
    async def valid_analysis(url, duration, **kw):
        wav.write_bytes(b"wav")
        return _decoded({"low": [0.1], "mid": [0.2], "high": [0.3]}, wav)

    async def fake_fb(*a, **k):
        return None

    _install_fake_analysis_service(monkeypatch)
    monkeypatch.setattr(main.auth_manager, "session", Session())
    monkeypatch.setattr(main, "analyze_stream", valid_analysis)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)

    await main.preview_analyzer("https://s/19", 12.0, 19)

    assert call_threads
    assert all(thread_id != event_loop_thread for thread_id in call_threads)


@pytest.mark.asyncio
async def test_local_hybrid_analysis_reads_temp_wav_not_network(monkeypatch, tmp_path):
    seen, deleted = {}, []
    wav = tmp_path / "preview.wav"
    wav.write_bytes(b"wav")

    async def fake_analyze(url, duration, **kw):
        return _decoded({"low": [0.5], "mid": [0.5], "high": [0.5]}, wav,
                        duration=10.0, fingerprint="b" * 64)

    async def fake_fb(*a, **k):
        return None

    _install_fake_analysis_service(monkeypatch, seen)
    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)

    async def fake_remove(path):
        deleted.append(path)
    monkeypatch.setattr(main, "_remove_temp_file", fake_remove)
    _fake_session_track(monkeypatch)

    result = await main.preview_analyzer(stream_url="https://s/11", duration=10.0, track_id=11)
    assert seen["wav_path"] == wav
    assert seen["pcm_sha256"] == "b" * 64
    assert deleted == [str(wav)]
    assert result["analysis"]["key"]["camelot"] == "4A"


@pytest.mark.asyncio
async def test_analysis_failure_raises_into_failed_snapshot(monkeypatch):
    async def fail(*a, **k):
        raise RuntimeError("decode died")

    async def none(_):
        return None

    monkeypatch.setattr(main, "analyze_stream", fail)
    monkeypatch.setattr(main.db, "get_waveform_cache", none)
    _fake_session_track(monkeypatch)
    with pytest.raises(RuntimeError):  # manager converts raised errors into failed snapshots
        await main.preview_analyzer(stream_url="https://s/13", duration=5.0, track_id=13)


@pytest.mark.asyncio
async def test_publish_progress_merges_and_bumps_revision():
    from backend.preview_jobs import PreviewJobManager

    manager = PreviewJobManager(analyzer=lambda *_: {})
    manager.start_or_get(21, "https://s/21", 100.0)

    manager.publish_progress(21, {"waveform": {"bands": {"low": [0.5]}}})
    snap = manager.snapshot(21)
    assert snap.status == "processing"
    assert snap.revision >= 2
    assert snap.waveform == {"bands": {"low": [0.5]}}

    manager.publish_progress(21, {"key": "Am", "camelot": "4A", "bpm": 128.0})
    snap = manager.snapshot(21)
    assert snap.key == "Am"
    assert snap.camelot == "4A"
    assert snap.bpm == 128.0
    assert snap.waveform == {"bands": {"low": [0.5]}}  # earlier fields preserved

    manager.publish_progress(999, {"key": "X"})  # unknown job: no-op, no raise


@pytest.mark.asyncio
async def test_metadata_poll_with_existing_job_skips_url_resolution(monkeypatch):
    track_calls, url_calls = [], []

    track = type("T", (), {
        "title": "t",
        "artist": type("A", (), {"name": "a"})(),
        "duration": 240.0,
        "get_url": staticmethod(lambda: url_calls.append(1) or "https://s/7"),
    })()
    session = type("S", (), {"track": staticmethod(lambda _id: track_calls.append(_id) or track),
                             "config": type("C", (), {"quality": "HIGH"})()})()
    monkeypatch.setattr(main.auth_manager, "session", session)
    monkeypatch.setattr(type(main.auth_manager), "is_authenticated",
                        property(lambda self: True))

    async def fast_analyzer(tid, url, duration):
        return {"waveform": {"bands": {"low": [0.1], "mid": [0.1], "high": [0.1]},
                             "colors": {}, "duration": duration or 0}}

    monkeypatch.setattr(main.preview_job_manager, "analyzer", fast_analyzer)

    first = await main.preview_metadata(7)
    assert track_calls == [7]
    assert len(url_calls) == 1

    second = await main.preview_metadata(7)
    # Second poll must not re-resolve the stream URL
    assert track_calls == [7]
    assert len(url_calls) == 1
    assert set(first) == set(second)  # same response shape


@pytest.mark.asyncio
async def test_temp_wav_removed_when_worker_fails(monkeypatch, tmp_path):
    deleted = []
    wav = tmp_path / "preview.wav"
    wav.write_bytes(b"wav")

    async def fake_analyze(url, duration, **kw):
        return _decoded({"low": [0.2], "mid": [0.2], "high": [0.2]}, wav,
                        duration=30.0)

    class FailingService:
        async def analyze_preview(self, **_kwargs):
            raise RuntimeError("analysis worker failed")

    async def fake_remove(path):
        deleted.append(path)

    async def no_provider(_tid):
        return {"provider_key": None, "provider_camelot": None, "provider_bpm": None}

    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main, "_get_analysis_service", lambda: FailingService())
    monkeypatch.setattr(main, "_preview_provider_metadata", no_provider)
    monkeypatch.setattr(main, "_remove_temp_file", fake_remove)

    with pytest.raises(RuntimeError, match="analysis worker failed"):
        await main.preview_analyzer(stream_url="https://s/15", duration=30.0, track_id=15)

    assert deleted == [str(wav)]
