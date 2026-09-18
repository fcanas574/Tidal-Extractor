import threading

import pytest
import backend.main as main


def _fake_session_track(monkeypatch):
    """auth_manager.session is None until the app lifespan logs in, so install a stub."""
    track = type("T", (), {"title": "t",
                           "artist": type("A", (), {"name": "a"})()})()
    session = type("S", (), {"track": staticmethod(lambda _id: track)})()
    monkeypatch.setattr(main.auth_manager, "session", session)


@pytest.mark.asyncio
async def test_uses_one_stream_and_persists(monkeypatch):
    calls = []

    async def fake_analyze(url, duration, **kw):
        calls.append(url)
        return {"bands": {"low": [0.1], "mid": [0.2], "high": [0.3]},
                "duration": 240.0, "temp_wav_path": None}

    async def none(_):
        return None

    saved = {}

    async def fake_set(tid, bands, duration):
        saved[tid] = bands

    async def fake_fb(*a, **k):
        return None

    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main.db, "get_waveform_cache", none)
    monkeypatch.setattr(main.db, "set_waveform_cache", fake_set)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    _fake_session_track(monkeypatch)

    result = await main.preview_analyzer(stream_url="https://s/7", duration=240.0, track_id=7)
    assert calls == ["https://s/7"]                    # exactly one download
    assert saved["7"]["low"] == [0.1]                  # persisted by tidal id
    assert result["waveform"]["bands"]["mid"] == [0.2]


@pytest.mark.asyncio
async def test_cache_hit_skips_download(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("must not download")

    async def hit(_):
        return {"bands": {"low": [1.0], "mid": [1.0], "high": [1.0]}, "duration": 12.0}

    monkeypatch.setattr(main, "analyze_stream", boom)
    monkeypatch.setattr(main.db, "get_waveform_cache", hit)
    result = await main.preview_analyzer(stream_url="https://s/9", duration=12.0, track_id=9)
    assert result["waveform"]["bands"]["high"] == [1.0]


@pytest.mark.asyncio
async def test_empty_waveform_cache_is_reanalyzed(monkeypatch):
    calls = []

    async def empty_cache(_):
        return {"bands": {"low": [], "mid": [], "high": []}, "duration": 12.0}

    async def fake_analyze(url, duration, **kw):
        calls.append(url)
        return {"bands": {"low": [0.1], "mid": [0.2], "high": [0.3]},
                "duration": 12.0, "temp_wav_path": None}

    async def fake_key_cache(_):
        return {}

    async def fake_fb(*a, **k):
        return None

    async def fake_set(*args):
        pass

    monkeypatch.setattr(main.db, "get_waveform_cache", empty_cache)
    monkeypatch.setattr(main, "_detect_preview_key_cached", fake_key_cache)
    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    monkeypatch.setattr(main.db, "set_waveform_cache", fake_set)
    _fake_session_track(monkeypatch)

    result = await main.preview_analyzer(stream_url="https://s/17", duration=12.0, track_id=17)

    assert calls == ["https://s/17"]
    assert result["waveform"]["bands"]["high"] == [0.3]


@pytest.mark.asyncio
async def test_empty_analysis_result_is_not_cached(monkeypatch):
    saved = []

    async def no_cache(_):
        return None

    async def empty_analysis(url, duration, **kw):
        return {"bands": {"low": [], "mid": [], "high": []},
                "duration": 12.0, "temp_wav_path": None}

    async def fake_fb(*a, **k):
        return None

    async def record_cache(*args):
        saved.append(args)

    monkeypatch.setattr(main.db, "get_waveform_cache", no_cache)
    monkeypatch.setattr(main, "analyze_stream", empty_analysis)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    monkeypatch.setattr(main.db, "set_waveform_cache", record_cache)
    _fake_session_track(monkeypatch)

    with pytest.raises(RuntimeError, match="no samples"):
        await main.preview_analyzer(stream_url="https://s/18", duration=12.0, track_id=18)

    assert saved == []


@pytest.mark.asyncio
async def test_preview_analyzer_resolves_track_off_event_loop(monkeypatch):
    event_loop_thread = threading.get_ident()
    call_threads = []

    class Session:
        def track(self, _track_id):
            call_threads.append(threading.get_ident())
            return type("T", (), {
                "title": "t",
                "artist": type("A", (), {"name": "a"})(),
            })()

    async def no_cache(_):
        return None

    async def valid_analysis(url, duration, **kw):
        return {"bands": {"low": [0.1], "mid": [0.2], "high": [0.3]},
                "duration": 12.0, "temp_wav_path": None}

    async def fake_fb(*a, **k):
        return None

    async def fake_set(*args):
        pass

    monkeypatch.setattr(main.auth_manager, "session", Session())
    monkeypatch.setattr(main.db, "get_waveform_cache", no_cache)
    monkeypatch.setattr(main, "analyze_stream", valid_analysis)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    monkeypatch.setattr(main.db, "set_waveform_cache", fake_set)

    await main.preview_analyzer("https://s/19", 12.0, 19)

    assert call_threads
    assert all(thread_id != event_loop_thread for thread_id in call_threads)


@pytest.mark.asyncio
async def test_local_key_detection_reads_temp_wav_not_network(monkeypatch):
    seen, deleted = {}, []

    async def fake_analyze(url, duration, **kw):
        return {"bands": {"low": [0.5], "mid": [0.5], "high": [0.5]},
                "duration": 10.0, "temp_wav_path": "/tmp/fake.wav"}

    async def fake_detect(path):
        seen["path"] = path
        return {"key": "Am", "camelot": "4A", "bpm": 128.0, "confidence": 0.9}

    async def fake_fb(*a, **k):
        return None

    async def fake_set_key(*a, **k):
        pass

    async def none(_):
        return None

    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main, "_detect_key_local", fake_detect)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    monkeypatch.setattr(main.db, "get_waveform_cache", none)
    monkeypatch.setattr(main.db, "set_key_cache", fake_set_key)
    monkeypatch.setattr(main.db, "set_waveform_cache", fake_set_key)

    async def fake_remove(path):
        deleted.append(path)
    monkeypatch.setattr(main, "_remove_temp_file", fake_remove)
    _fake_session_track(monkeypatch)

    result = await main.preview_analyzer(stream_url="https://s/11", duration=10.0, track_id=11)
    assert seen["path"] == "/tmp/fake.wav"
    assert deleted == ["/tmp/fake.wav"]
    assert result["camelot"] == "4A"


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
async def test_temp_wav_removed_even_when_db_write_fails(monkeypatch):
    deleted = []

    async def fake_analyze(url, duration, **kw):
        return {"bands": {"low": [0.2], "mid": [0.2], "high": [0.2]},
                "duration": 30.0, "temp_wav_path": "/tmp/fake.wav"}

    async def failing_set(tid, bands, duration):
        raise RuntimeError("db write exploded")

    async def none(_):
        return None

    async def fake_remove(path):
        deleted.append(path)

    async def fake_fb(*a, **k):
        return None

    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main.db, "get_waveform_cache", none)
    monkeypatch.setattr(main.db, "set_waveform_cache", failing_set)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    monkeypatch.setattr(main, "_remove_temp_file", fake_remove)
    _fake_session_track(monkeypatch)

    # DB failure must not propagate or block cleanup
    result = await main.preview_analyzer(stream_url="https://s/15", duration=30.0, track_id=15)
    assert deleted == ["/tmp/fake.wav"]  # temp WAV removed despite DB error
    assert result["waveform"]["bands"]["low"] == [0.2]
