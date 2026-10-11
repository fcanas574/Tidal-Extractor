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
        "https://example.test/stream?asset=one",
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
        "https://example.test/stream?asset=one",
        240.0,
        **identity,
    )
    assert replacement.status == "queued"
    manager.run_pending_for_test()

    assert len(calls) == 2
    assert manager.snapshot(12).waveform == {"points": [2]}


@pytest.mark.parametrize(
    ("old_query", "new_query"),
    [
        ("asset=one&token=old", "asset=one&token=new"),
        ("asset=one&auth=old", "asset=one&auth=new"),
        ("asset=one&X-Amz-Credential=old", "asset=one&X-Amz-Credential=new"),
        ("asset=one&X-Goog-Signature=old", "asset=one&X-Goog-Signature=new"),
    ],
    ids=["generic-token", "generic-auth", "aws-query", "google-query"],
)
def test_unverified_query_parameters_are_preserved_in_preview_identity(old_query, new_query):
    calls = []

    def analyzer(stream_url, duration, *_args, **_kwargs):
        calls.append(stream_url)
        return {"waveform": {"points": [len(calls)]}}

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(
        12,
        f"https://example.test/stream?{old_query}",
        240.0,
        preview_profile="LOW",
        decoder_version="decoder-v1",
        settings_identity="settings-v1",
    )
    manager.run_pending_for_test()
    refreshed = manager.start_or_get(
        12,
        f"https://example.test/stream?{new_query}",
        240.0,
        preview_profile="LOW",
        decoder_version="decoder-v1",
        settings_identity="settings-v1",
    )
    assert refreshed.status == "queued"
    manager.run_pending_for_test()

    assert len(calls) == 2
    assert manager.snapshot(12).waveform == {"points": [2]}


@pytest.mark.asyncio
async def test_superseded_jobs_share_the_five_task_cap_and_stale_result_cannot_publish():
    urls = [
        "https://example.test/old",
        "https://example.test/other-2",
        "https://example.test/other-3",
        "https://example.test/other-4",
        "https://example.test/new",
        "https://example.test/admitted-after-drain",
    ]
    started = {url: asyncio.Event() for url in urls}
    finished = {url: asyncio.Event() for url in urls}
    release = {url: asyncio.Event() for url in urls}

    async def analyzer(stream_url, _duration, _track_id, on_snapshot=None):
        started[stream_url].set()
        await release[stream_url].wait()
        if stream_url.endswith("/old"):
            await on_snapshot({"waveform": {"points": ["stale"]}})
            result = {"waveform": {"points": ["stale"]}}
        else:
            result = {"waveform": {"points": [stream_url.rsplit("/", 1)[-1]]}}
        finished[stream_url].set()
        return result

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(1, urls[0], 10.0)
    await asyncio.wait_for(started[urls[0]].wait(), timeout=1)
    for track_id, stream_url in zip((2, 3, 4), urls[1:4]):
        manager.start_or_get(track_id, stream_url, 10.0)
        await asyncio.wait_for(started[stream_url].wait(), timeout=1)

    manager.start_or_get(1, urls[4], 10.0)
    await asyncio.wait_for(started[urls[4]].wait(), timeout=1)
    assert manager.active_job_count() == 5  # four waiting/current sources plus the retired source

    try:
        with pytest.raises(RuntimeError, match="capacity|queue"):
            manager.start_or_get(5, urls[5], 10.0)
        assert manager.snapshot(5) is None
        assert manager.active_job_count() == 5

        release[urls[0]].set()
        await asyncio.wait_for(finished[urls[0]].wait(), timeout=1)
        await asyncio.sleep(0)
        current = manager.snapshot(1)
        assert current is not None
        assert current.waveform is None
        assert manager.active_job_count() == 4

        # The rejected source can be admitted once a slot frees.
        manager.start_or_get(5, urls[5], 10.0)
        await asyncio.wait_for(started[urls[5]].wait(), timeout=1)
        assert manager.active_job_count() == 5
    finally:
        for event in release.values():
            event.set()
        while manager.active_job_count():
            await asyncio.sleep(0)

    current = manager.snapshot(1)
    assert current is not None
    assert current.waveform == {"points": ["new"]}
    assert manager.active_job_count() == 0


@pytest.mark.asyncio
async def test_retry_stays_failed_when_capacity_is_full_and_can_be_retried_later():
    retry_started = asyncio.Event()
    release_retry = asyncio.Event()
    release_waiters = asyncio.Event()
    waiting_started = {track_id: asyncio.Event() for track_id in range(2, 7)}

    async def analyzer(_url, _duration, track_id, **_kwargs):
        if track_id == 1:
            raise RuntimeError("analysis failed")
        waiting_started[track_id].set()
        await release_waiters.wait()
        return {"waveform": {"points": [track_id]}}

    async def analysis_retry(_url, _duration, _track_id):
        retry_started.set()
        await release_retry.wait()
        return {"analysis_status": "complete"}

    manager = PreviewJobManager(analyzer=analyzer, analysis_retry=analysis_retry)
    manager.start_or_get(1, "https://example.test/failed", 10.0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert manager.snapshot(1).analysis_status == "failed"

    for track_id in waiting_started:
        manager.start_or_get(track_id, f"https://example.test/{track_id}", 10.0)
    await asyncio.gather(*(event.wait() for event in waiting_started.values()))
    assert manager.active_job_count() == 5

    try:
        with pytest.raises(RuntimeError, match="capacity|queue"):
            manager.retry_analysis(1)
        assert manager.snapshot(1).analysis_status == "failed"
    finally:
        release_waiters.set()
        while manager.active_job_count():
            await asyncio.sleep(0)

    retried = manager.retry_analysis(1)
    assert retried is not None
    assert retried.analysis_status == "queued"
    await asyncio.wait_for(retry_started.wait(), timeout=1)
    release_retry.set()
    while manager.active_job_count():
        await asyncio.sleep(0)
    assert manager.snapshot(1).analysis_status == "complete"


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
