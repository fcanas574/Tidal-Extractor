import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time

import pytest

from backend.analysis.worker import QueueWaiterReplaced
from backend.preview_jobs import PreviewJobManager, _source_identity


async def _wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition did not become true before timeout")
        await asyncio.sleep(0.01)


def test_start_or_get_is_idempotent():
    manager = PreviewJobManager(analyzer=lambda *_, **__: {})
    first = manager.start_or_get(12, "https://example.test/stream", 240.0)
    second = manager.start_or_get(12, "https://example.test/stream", 240.0)
    assert first.track_id == second.track_id == 12
    assert manager.active_job_count() == 1
    manager.run_pending_for_test()


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


def test_source_identity_preserves_stable_query_selectors():
    first = _source_identity("https://example.test/stream?asset=one&quality=high")
    second = _source_identity("https://example.test/stream?asset=two&quality=high")

    assert first != second


@pytest.mark.parametrize(
    ("old_parameter", "new_parameter"),
    [
        ("token=old", "token=new"),
        ("auth=old", "AUTH=new"),
        ("access_token=old", "ACCESS_TOKEN=new"),
        ("signature=old", "Signature=new"),
        ("sig=old", "SIG=new"),
        ("expires=100", "EXPIRES=200"),
        ("expiry=100", "Expiry=200"),
        ("X-Amz-Credential=old", "x-amz-credential=new"),
        ("X-Amz-Signature=old", "x-amz-signature=new"),
        ("X-Goog-Signature=old", "x-goog-signature=new"),
        ("X-Goog-Expires=100", "x-goog-expires=200"),
        ("HDNEA=old", "hdnea=new"),
        ("HDNTS=old", "hdnts=new"),
    ],
    ids=[
        "token",
        "auth",
        "access-token",
        "signature",
        "sig",
        "expires",
        "expiry",
        "aws-credential",
        "aws-signature",
        "google-signature",
        "google-expiry",
        "hdnea",
        "hdnts",
    ],
)
def test_source_identity_ignores_rotating_auth_parameters(old_parameter, new_parameter):
    first = _source_identity(f"https://example.test/stream?asset=one&{old_parameter}")
    second = _source_identity(f"https://example.test/stream?asset=one&{new_parameter}")

    assert first == second


def test_source_identity_preserves_unrelated_query_parameters():
    first = _source_identity("https://example.test/stream?asset=one&variant=original")
    second = _source_identity("https://example.test/stream?asset=one&variant=changed")

    assert first != second


def test_rotating_cdn_token_url_reuses_completed_preview_snapshot():
    calls = []

    def analyzer(stream_url, duration, *_args, **_kwargs):
        calls.append((stream_url, duration))
        return {"waveform": {"points": [len(calls)]}}

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(12, "https://example.test/stream?asset=one&hdnea=old", 240.0)
    manager.run_pending_for_test()
    completed = manager.snapshot(12)

    refreshed = manager.start_or_get(
        12,
        "https://example.test/stream?asset=one&HDNEA=new",
        240.0,
    )

    assert completed is not None
    assert refreshed.status == completed.status == "complete"
    assert refreshed.waveform == completed.waveform == {"points": [1]}
    assert len(calls) == 1


def test_explicit_retry_uses_latest_signed_source_url():
    analyzed_urls = []
    retried_urls = []

    def analyzer(stream_url, *_args, **_kwargs):
        analyzed_urls.append(stream_url)
        raise RuntimeError("initial analysis failed")

    def analysis_retry(stream_url, *_args, **_kwargs):
        retried_urls.append(stream_url)
        return {"analysis_status": "complete"}

    manager = PreviewJobManager(analyzer=analyzer, analysis_retry=analysis_retry)
    original_url = "https://example.test/stream?asset=one&token=old&expires=100"
    refreshed_url = "https://example.test/stream?asset=one&token=new&expires=200"
    manager.start_or_get(12, original_url, 240.0)
    manager.run_pending_for_test()
    assert manager.snapshot(12).analysis_status == "failed"

    manager.start_or_get(12, refreshed_url, 240.0)
    queued = manager.retry_analysis(12)
    assert queued is not None
    assert queued.analysis_status == "queued"
    manager.run_pending_for_test()

    assert analyzed_urls == [original_url]
    assert retried_urls == [refreshed_url]


@pytest.mark.asyncio
async def test_new_sources_are_admitted_and_stale_result_cannot_publish():
    old_url = "https://example.test/old"
    new_url = "https://example.test/new"
    active_started = asyncio.Event()
    release = asyncio.Event()
    analyzed = []

    async def analyzer(stream_url, _duration, track_id, on_snapshot=None):
        analyzed.append((track_id, stream_url))
        if stream_url == old_url:
            active_started.set()
        await release.wait()
        if stream_url == old_url:
            await on_snapshot({"waveform": {"points": ["stale"]}})
            return {"waveform": {"points": ["stale"]}}
        return {"waveform": {"points": [stream_url.rsplit("/", 1)[-1]]}}

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(1, old_url, 10.0)
    await asyncio.wait_for(active_started.wait(), timeout=1)
    for track_id in (2, 3, 4):
        manager.start_or_get(track_id, f"https://example.test/{track_id}", 10.0)

    # A changed source for the active track waits behind its still-running old
    # source. The manager admits only four waiters and replaces the oldest when
    # a fifth new identity arrives.
    manager.start_or_get(1, new_url, 10.0)
    manager.start_or_get(5, "https://example.test/5", 10.0)
    assert manager.active_job_count() == 5  # one active decode plus four waiters
    assert analyzed == [(1, old_url)]

    displaced = manager.snapshot(2)
    assert displaced is not None
    assert displaced.analysis_status == "deferred"
    assert "replaced by newer work" in displaced.analysis_error

    release.set()
    await _wait_until(lambda: manager.snapshot(1).waveform == {"points": ["new"]})
    await _wait_until(lambda: manager.active_job_count() == 0)
    current = manager.snapshot(1)
    assert current is not None
    assert current.waveform == {"points": ["new"]}
    assert manager.active_job_count() == 0


@pytest.mark.asyncio
async def test_retry_reenters_bounded_manager_admission():
    active_started = asyncio.Event()
    release_active = asyncio.Event()
    retry_started = asyncio.Event()
    calls = []

    async def analyzer(_url, _duration, track_id, **_kwargs):
        calls.append(track_id)
        if track_id == 1:
            raise RuntimeError("analysis failed")
        active_started.set()
        await release_active.wait()
        return {"waveform": {"points": [track_id]}}

    async def analysis_retry(_url, _duration, track_id, **_kwargs):
        calls.append(("retry", track_id))
        retry_started.set()
        return {"analysis_status": "complete"}

    manager = PreviewJobManager(analyzer=analyzer, analysis_retry=analysis_retry)
    manager.start_or_get(1, "https://example.test/failed", 10.0)
    await _wait_until(lambda: manager.snapshot(1).analysis_status == "failed")

    manager.start_or_get(2, "https://example.test/2", 10.0)
    await active_started.wait()
    for track_id in range(3, 7):
        manager.start_or_get(track_id, f"https://example.test/{track_id}", 10.0)

    retried = manager.retry_analysis(1)
    assert retried is not None
    assert retried.analysis_status == "queued"
    assert manager.active_job_count() == 5
    assert manager.snapshot(3).analysis_status == "deferred"
    assert calls == [1, 2]

    release_active.set()
    await asyncio.wait_for(retry_started.wait(), timeout=2)
    await _wait_until(lambda: manager.snapshot(1).analysis_status == "complete")
    await _wait_until(lambda: manager.active_job_count() == 0)


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
    new_started = asyncio.Event()
    new_finished = asyncio.Event()

    async def analyzer(stream_url, _duration, _track_id, on_snapshot=None):
        if stream_url.endswith("old"):
            old_started.set()
            await release_old.wait()
            await on_snapshot({"waveform": {"points": ["stale"]}})
            old_finished.set()
            return {"waveform": {"points": ["stale"]}}
        new_started.set()
        result = {"waveform": {"points": ["current"]}}
        new_finished.set()
        return result

    manager = PreviewJobManager(analyzer=analyzer)
    manager.start_or_get(12, "https://example.test/old", 240.0)
    await asyncio.wait_for(old_started.wait(), timeout=1)
    manager.start_or_get(12, "https://example.test/new", 180.0)
    try:
        await asyncio.sleep(0)
        assert not new_started.is_set()

        release_old.set()
        await asyncio.wait_for(old_finished.wait(), timeout=1)
        await asyncio.wait_for(new_finished.wait(), timeout=1)
        await _wait_until(lambda: manager.active_job_count() == 0)

        current = manager.snapshot(12)
        assert current is not None
        assert current.waveform == {"points": ["current"]}
    finally:
        release_old.set()
        await manager.close()


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


@pytest.mark.asyncio
async def test_manager_queue_replacement_is_deferred_without_decode_and_can_be_retried():
    active_started = asyncio.Event()
    release_active = asyncio.Event()
    analyzed_tracks = []
    retried_tracks = []

    async def analyzer(_url, _duration, track_id, **_kwargs):
        analyzed_tracks.append(track_id)
        if track_id == 1:
            active_started.set()
            await release_active.wait()
        return {"analysis_status": "complete"}

    async def retry(_url, _duration, track_id, **_kwargs):
        retried_tracks.append(track_id)
        return {"analysis_status": "complete"}

    manager = PreviewJobManager(analyzer=analyzer, analysis_retry=retry)
    urls = {track_id: f"https://example.test/{track_id}" for track_id in range(1, 7)}
    manager.start_or_get(1, urls[1], 10.0)
    await active_started.wait()
    for track_id in range(2, 6):
        manager.start_or_get(track_id, urls[track_id], 10.0)

    admitted = manager.start_or_get(6, urls[6], 10.0)
    assert admitted.track_id == 6
    assert manager.active_job_count() == 5
    assert analyzed_tracks == [1]

    deferred = manager.snapshot(2)
    assert deferred is not None
    assert deferred.analysis_status == "deferred"
    assert deferred.analysis_error is not None
    assert "replaced by newer work" in deferred.analysis_error
    assert deferred.error == deferred.analysis_error

    polled = manager.start_or_get(2, urls[2], 10.0)
    assert polled.analysis_status == "deferred"
    assert analyzed_tracks == [1]

    release_active.set()
    await _wait_until(lambda: manager.active_job_count() == 0)

    retry_snapshot = manager.retry_analysis(2)
    assert retry_snapshot is not None
    assert retry_snapshot.analysis_status == "queued"
    await _wait_until(
        lambda: (snapshot := manager.snapshot(2)) is not None
        and snapshot.analysis_status == "complete"
    )
    assert retried_tracks == [2]
    assert 2 not in analyzed_tracks
    assert analyzed_tracks == [1, 3, 4, 5, 6]


def test_worker_queue_replacement_error_is_deferred_and_explicitly_retryable():
    analyzer_calls = []
    retry_calls = []

    def analyzer(stream_url, *_args, **_kwargs):
        analyzer_calls.append(stream_url)
        raise QueueWaiterReplaced("worker waiter was replaced by newer work")

    def retry(stream_url, *_args, **_kwargs):
        retry_calls.append(stream_url)
        return {"analysis_status": "complete"}

    manager = PreviewJobManager(analyzer=analyzer, analysis_retry=retry)
    source_url = "https://example.test/stream"
    manager.start_or_get(12, source_url, 10.0)
    manager.run_pending_for_test()

    deferred = manager.snapshot(12)
    assert deferred is not None
    assert deferred.analysis_status == "deferred"
    assert deferred.analysis_error == "worker waiter was replaced by newer work"
    assert deferred.error == deferred.analysis_error
    assert analyzer_calls == [source_url]

    assert manager.start_or_get(12, source_url, 10.0).analysis_status == "deferred"
    assert analyzer_calls == [source_url]
    assert manager.retry_analysis(12).analysis_status == "queued"
    manager.run_pending_for_test()

    assert retry_calls == [source_url]
    assert manager.snapshot(12).analysis_status == "complete"


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

    async def analysis_retry(*_args, **_kwargs):
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
