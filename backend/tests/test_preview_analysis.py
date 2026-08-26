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

    result = await main.preview_analyzer(7, "https://s/7", 240.0)
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
    result = await main.preview_analyzer(9, "https://s/9", 12.0)
    assert result["waveform"]["bands"]["high"] == [1.0]


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

    result = await main.preview_analyzer(11, "https://s/11", 10.0)
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
        await main.preview_analyzer(13, "https://s/13", 5.0)


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
