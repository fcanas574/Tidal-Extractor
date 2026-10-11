import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from backend.preview_jobs import PreviewJobManager


def test_start_or_get_is_idempotent():
    manager = PreviewJobManager(analyzer=lambda *_, **__: {})
    first = manager.start_or_get(12, "https://example.test/stream", 240.0)
    second = manager.start_or_get(12, "https://example.test/stream", 240.0)
    assert first.track_id == second.track_id == 12
    assert manager.active_job_count() == 1


@pytest.mark.parametrize(
    ("next_url", "next_duration"),
    [
        ("https://example.test/replacement-stream", 240.0),
        ("https://example.test/stream", 180.0),
    ],
    ids=["changed-source", "changed-duration"],
)
def test_completed_snapshot_is_not_reused_for_changed_preview_identity(
    next_url, next_duration,
):
    calls = []

    def analyzer(stream_url, duration, *_args, **_kwargs):
        calls.append((stream_url, duration))
        return {"waveform": {"points": [len(calls)]}}

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(12, "https://example.test/stream", 240.0)
    manager.run_pending_for_test()

    replacement = manager.start_or_get(12, next_url, next_duration)
    assert replacement.status == "queued"
    manager.run_pending_for_test()

    assert calls == [
        ("https://example.test/stream", 240.0),
        (next_url, next_duration),
    ]
    assert manager.snapshot(12).waveform == {"points": [2]}


@pytest.mark.parametrize(
    "changed_identity",
    [
        {"preview_profile": "HIGH"},
        {"decoder_version": "decoder-v2"},
        {"settings_identity": "settings-v2"},
    ],
    ids=["changed-profile", "changed-decoder", "changed-settings"],
)
def test_completed_snapshot_is_not_reused_after_engine_identity_changes(changed_identity):
    calls = []

    def analyzer(stream_url, duration, *_args, **_kwargs):
        calls.append((stream_url, duration))
        return {"waveform": {"points": [len(calls)]}}

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(
        12,
        "https://example.test/stream?asset=one&token=old",
        240.0,
        preview_profile="LOW",
        decoder_version="decoder-v1",
        settings_identity="settings-v1",
    )
    manager.run_pending_for_test()

    identity = {
        "preview_profile": "LOW",
        "decoder_version": "decoder-v1",
        "settings_identity": "settings-v1",
    }
    identity.update(changed_identity)
    replacement = manager.start_or_get(
        12,
        "https://example.test/stream?asset=one&token=new",
        240.0,
        **identity,
    )
    assert replacement.status == "queued"
    manager.run_pending_for_test()

    assert len(calls) == 2
    assert manager.snapshot(12).waveform == {"points": [2]}


def test_rotating_signed_url_reuses_matching_preview_alias_within_24_hours():
    calls = []

    def analyzer(stream_url, duration, *_args, **_kwargs):
        calls.append(stream_url)
        return {"waveform": {"points": [1]}}

    manager = PreviewJobManager(analyzer=analyzer)
    first = manager.start_or_get(
        12,
        "https://example.test/stream?asset=one&token=old",
        240.0,
        preview_profile="LOW",
        decoder_version="decoder-v1",
        settings_identity="settings-v1",
    )
    manager.run_pending_for_test()
    refreshed = manager.start_or_get(
        12,
        "https://example.test/stream?token=new&asset=one",
        240.0,
        preview_profile="LOW",
        decoder_version="decoder-v1",
        settings_identity="settings-v1",
    )

    assert refreshed.status == "complete"
    assert refreshed.revision == manager.snapshot(12).revision
    assert first.revision < refreshed.revision
    assert calls == ["https://example.test/stream?asset=one&token=old"]


def test_completed_snapshot_expires_after_24_hours():
    now = [datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)]
    calls = []

    def analyzer(*_args, **_kwargs):
        calls.append("analyzed")
        return {"waveform": {"points": [len(calls)]}}

    manager = PreviewJobManager(analyzer=analyzer, clock=lambda: now[0])
    manager.start_or_get(12, "https://example.test/stream", 240.0)
    manager.run_pending_for_test()
    now[0] += timedelta(hours=24)

    assert manager.snapshot(12) is None
    replacement = manager.start_or_get(12, "https://example.test/stream", 240.0)
    assert replacement.status == "queued"
    manager.run_pending_for_test()

    assert calls == ["analyzed", "analyzed"]


def test_completed_snapshot_retention_is_bounded():
    manager = PreviewJobManager(
        analyzer=lambda *_args, **_kwargs: {"waveform": {"points": [1]}},
        max_retained_snapshots=2,
    )
    for track_id in (1, 2, 3):
        manager.start_or_get(track_id, f"https://example.test/{track_id}", 10.0)
        manager.run_pending_for_test()

    assert manager.snapshot(1) is None
    assert manager.snapshot(2) is not None
    assert manager.snapshot(3) is not None


@pytest.mark.asyncio
async def test_superseded_in_progress_result_cannot_publish_to_current_snapshot():
    old_started = asyncio.Event()
    release_old = asyncio.Event()
    old_finished = asyncio.Event()
    new_finished = asyncio.Event()

    async def analyzer(stream_url, _duration, _track_id, on_snapshot=None):
        if stream_url.endswith("old"):
            old_started.set()
            await release_old.wait()
            await on_snapshot({"waveform": {"points": ["stale"]}})
            old_finished.set()
            return {"waveform": {"points": ["stale"]}}
        result = {"waveform": {"points": ["current"]}}
        new_finished.set()
        return result

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(12, "https://example.test/old", 240.0)
    await asyncio.wait_for(old_started.wait(), timeout=1)
    manager.start_or_get(12, "https://example.test/new", 180.0)
    await asyncio.wait_for(new_finished.wait(), timeout=1)
    await asyncio.sleep(0)

    release_old.set()
    await asyncio.wait_for(old_finished.wait(), timeout=1)
    await asyncio.sleep(0)

    current = manager.snapshot(12)
    assert current is not None
    assert current.waveform == {"points": ["current"]}


def test_snapshot_reports_failed_job():
    manager = PreviewJobManager(
        analyzer=lambda *_, **__: (_ for _ in ()).throw(RuntimeError("decode failed"))
    )
    manager.start_or_get(12, "https://example.test/stream", 240.0)
    manager.run_pending_for_test()
    snapshot = manager.snapshot(12)
    assert snapshot is not None
    assert snapshot.status == "failed"
    assert snapshot.error == "decode failed"


@pytest.mark.asyncio
async def test_start_or_get_runs_job_on_active_loop_without_test_pump():
    started = asyncio.Event()

    async def analyzer(*_args, **kwargs):
        started.set()
        return {"waveform": {"points": [1, 2, 3]}, "bpm": 128.0}

    manager = PreviewJobManager(analyzer=analyzer)

    manager.start_or_get(12, "https://example.test/stream", 240.0)

    await asyncio.wait_for(started.wait(), timeout=1)

    snapshot = manager.snapshot(12)
    assert snapshot is not None
    assert snapshot.status in {"processing", "complete"}


@pytest.mark.asyncio
async def test_waveform_completion_does_not_finish_analysis():
    analysis_started = asyncio.Event()
    finish_analysis = asyncio.Event()
    waveform = {
        "bands": {"low": [0.1], "mid": [0.2], "high": [0.3]},
        "duration": 10.0,
    }

    async def analyzer(*_args, on_snapshot=None):
        await on_snapshot({**waveform, "complete": True})
        analysis_started.set()
        await finish_analysis.wait()
        return {
            "waveform": waveform,
            "analysis_status": "complete",
            "analysis": {"key": {"key": "G", "camelot": "9B"}},
        }

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(12, "https://example.test/stream", 10.0)
    await asyncio.wait_for(analysis_started.wait(), timeout=1)

    snapshot = manager.snapshot(12)
    assert snapshot is not None
    assert snapshot.status == "processing"
    assert snapshot.waveform_status == "complete"
    assert snapshot.analysis_status == "processing"
    assert snapshot.waveform == waveform

    finish_analysis.set()
    await asyncio.sleep(0)
    snapshot = manager.snapshot(12)
    assert snapshot is not None
    assert snapshot.status == "complete"


def test_analysis_failure_keeps_waveform_as_partial():
    waveform = {
        "bands": {"low": [0.1], "mid": [0.2], "high": [0.3]},
        "duration": 10.0,
    }

    async def analyzer(*_args, on_snapshot=None):
        await on_snapshot({**waveform, "complete": True})
        raise RuntimeError("analysis worker unavailable")

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(12, "https://example.test/stream", 10.0)
    manager.run_pending_for_test()

    snapshot = manager.snapshot(12)
    assert snapshot is not None
    assert snapshot.status == "partial"
    assert snapshot.waveform_status == "complete"
    assert snapshot.analysis_status == "failed"
    assert snapshot.analysis_error == "analysis worker unavailable"
    assert snapshot.waveform == waveform


def test_unknown_analysis_with_usable_waveform_is_terminal_partial():
    waveform = {
        "bands": {"low": [0.1], "mid": [0.2], "high": [0.3]},
        "duration": 10.0,
    }

    async def analyzer(*_args, on_snapshot=None):
        await on_snapshot({**waveform, "complete": True})
        return {"analysis_status": "unknown", "analysis_error": "no usable result"}

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(12, "https://example.test/stream", 10.0)
    manager.run_pending_for_test()

    snapshot = manager.snapshot(12)
    assert snapshot is not None
    assert snapshot.status == "partial"
    assert snapshot.waveform_status == "complete"
    assert snapshot.analysis_status == "unknown"
    assert snapshot.waveform == waveform


def test_explicit_retry_requeues_failed_analysis_once():
    retry_calls = 0
    waveform = {
        "bands": {"low": [0.1], "mid": [0.2], "high": [0.3]},
        "duration": 10.0,
    }

    async def analyzer(*_args, **_kwargs):
        return {
            "waveform": waveform,
            "analysis_status": "failed",
            "analysis_error": "model unavailable",
        }

    async def analysis_retry(*_args):
        nonlocal retry_calls
        retry_calls += 1
        return {
            "analysis_status": "complete",
            "analysis_error": None,
            "analysis": {"key": {"key": "G", "camelot": "9B"}},
        }

    manager = PreviewJobManager(analyzer=analyzer, analysis_retry=analysis_retry)
    manager.start_or_get(12, "https://example.test/stream", 10.0)
    manager.run_pending_for_test()
    assert manager.snapshot(12).status == "partial"

    queued = manager.retry_analysis(12)
    assert queued.analysis_status == "queued"
    manager.run_pending_for_test()
    complete = manager.snapshot(12)
    assert complete.status == "complete"
    assert complete.waveform == waveform
    assert complete.key == "G"
    assert retry_calls == 1

    manager.retry_analysis(12)
    manager.run_pending_for_test()
    assert retry_calls == 1


def test_local_grid_bpm_is_not_provider_bpm():
    async def analyzer(*_args, **_kwargs):
        return {
            "analysis_status": "complete",
            "analysis": {
                "key": {"key": "G", "camelot": "9B", "status": "reliable"},
                "rhythm": {
                    "bpm": 127.5,
                    "grid": {"bpm": 127.5, "status": "reliable"},
                },
            },
            "provider_key": "A",
            "provider_camelot": "8A",
            "provider_bpm": 111.0,
        }

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(12, "https://example.test/stream", 10.0)
    manager.run_pending_for_test()

    snapshot = manager.snapshot(12)
    assert snapshot is not None
    assert snapshot.bpm == 127.5
    assert snapshot.bpm_source == "local"
    assert snapshot.provider_bpm == 111.0
    assert snapshot.provider_key == "A"
    assert snapshot.provider_camelot == "8A"
    assert snapshot.key == "G"
    assert snapshot.key_source == "local"


def test_stale_local_null_clears_previous_values():
    initial_analysis = {
        "key": {"key": "C", "camelot": "8B", "status": "reliable"},
        "rhythm": {"grid": {"bpm": 120.0, "status": "reliable"}},
    }
    cleared_analysis = {
        "key": {"key": None, "camelot": None, "status": "unknown"},
        "rhythm": {"grid": {"bpm": None, "status": "unavailable"}},
    }
    async def analyzer(*_args, **_kwargs):
        return {
            "analysis_status": "complete",
            "analysis": deepcopy(initial_analysis),
        }

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(12, "https://example.test/stream", 10.0)
    manager.run_pending_for_test()
    manager.publish_progress(12, {"analysis": cleared_analysis})

    snapshot = manager.snapshot(12)
    assert snapshot is not None
    assert snapshot.analysis == cleared_analysis
    assert snapshot.key is None
    assert snapshot.camelot is None
    assert snapshot.bpm is None
