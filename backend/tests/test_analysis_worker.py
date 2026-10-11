import asyncio
from datetime import datetime, timezone
import hashlib
import multiprocessing
import os
from pathlib import Path
import signal
import time

import pytest

from backend.analysis.types import (
    AnalysisSettings,
    GridResult,
    HybridAnalysisResult,
    KeyCandidate,
    KeyResult,
    RhythmResult,
)
from backend.analysis.worker import AnalysisWorker, QueueWaiterReplaced


def _result(job_id, settings, *, rhythm_status="reliable"):
    fingerprint = job_id if len(job_id) == 64 else hashlib.sha256(job_id.encode()).hexdigest()
    return HybridAnalysisResult(
        schema_version=settings.schema_version,
        audio_fingerprint=fingerprint,
        decoder_version="test-decoder",
        duration_seconds=1.0,
        model_id=settings.model_id,
        model_sha256="b" * 64,
        key_profile_id=settings.key_profile_id,
        settings_sha256=settings.sha256,
        key=KeyResult(
            key="C major",
            camelot="8B",
            status="reliable",
            candidates=(KeyCandidate(0, "major", 0.9),),
            agreement=1.0,
            reason=None,
        ),
        rhythm=RhythmResult(
            bpm=None,
            beats=(),
            downbeats=(),
            grid=GridResult(
                bpm=None,
                period_seconds=None,
                origin_seconds=None,
                meter=None,
                first_downbeat_beat=None,
                status=rhythm_status,
                residual_p95_seconds=None,
                split_drift_seconds=None,
                reason="mocked rhythm failure" if rhythm_status == "failed" else None,
            ),
            status=rhythm_status,
            reason="mocked rhythm failure" if rhythm_status == "failed" else None,
        ),
    )


def _fake_worker_loop(command_receiver, result_sender, *args):
    control_path = Path(args[0]) if args else None
    started_event = args[1] if len(args) > 1 else None
    result_sender.send({"kind": "ready"})
    first_command = True
    while True:
        command = command_receiver.recv()
        if command["kind"] == "stop":
            return
        if first_command and started_event is not None:
            started_event.set()
        first_command = False
        audio_path = Path(command["wav_path"])
        payload = audio_path.read_bytes()
        if payload == b"block":
            while control_path is not None and not control_path.exists():
                time.sleep(0.01)
        if payload == b"crash":
            os._exit(17)
        rhythm_status = "failed" if payload == b"rhythm-error" else "reliable"
        result_sender.send(
            {
                "kind": "result",
                "job_id": command["job_id"],
                "result": _result(command["job_id"], command["settings"], rhythm_status=rhythm_status),
            }
        )


def _terminating_worker_loop(
    command_receiver, result_sender, marker_path, started_event, terminating_event, allow_exit
):
    marker_path = Path(marker_path)
    current_path = None

    def on_terminate(_signum, _frame):
        marker_path.write_text(str(current_path.is_file()), encoding="utf-8")
        terminating_event.set()
        allow_exit.wait(3)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_terminate)
    result_sender.send({"kind": "ready"})
    command = command_receiver.recv()
    current_path = Path(command["wav_path"])
    started_event.set()
    while True:
        time.sleep(0.02)


def _wav(tmp_path, name, contents=b"audio"):
    path = tmp_path / name
    path.write_bytes(contents)
    return path


def test_worker_limits_waiting_sources_and_execution_timeout():
    with pytest.raises(ValueError, match="max_waiting"):
        AnalysisWorker(max_waiting=5)
    with pytest.raises(ValueError, match="execution_timeout"):
        AnalysisWorker(execution_timeout=180.1)


async def _wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition did not become true before timeout")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_worker_starts_only_after_submit(tmp_path):
    worker = AnalysisWorker(worker_target=_fake_worker_loop)
    assert worker.active_worker_count == 0
    assert worker.worker_start_count == 0
    try:
        result = await worker.submit("a" * 64, _wav(tmp_path, "one.wav"), AnalysisSettings())
        assert result.key.status == "reliable"
        assert worker.worker_start_count == 1
        assert worker.active_worker_count == 1
    finally:
        await worker.close()


@pytest.mark.asyncio
async def test_worker_queue_is_bounded_and_replaces_oldest_waiter(tmp_path):
    context = multiprocessing.get_context("spawn")
    release_path = tmp_path / "release"
    started = context.Event()
    worker = AnalysisWorker(
        worker_target=_fake_worker_loop,
        worker_target_args=(str(release_path), started),
        max_waiting=4,
    )
    active = asyncio.create_task(worker.submit("active", _wav(tmp_path, "active.wav", b"block"), AnalysisSettings()))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        queued = []
        for index in range(4):
            queued.append(
                asyncio.create_task(
                    worker.submit(
                        f"queued-{index}",
                        _wav(tmp_path, f"queued-{index}.wav"),
                        AnalysisSettings(),
                    )
                )
            )
            await _wait_until(lambda: worker.queued_source_count == index + 1)
        replaced_wav = worker.managed_paths["queued-0"]
        queued.append(
            asyncio.create_task(
                worker.submit("queued-4", _wav(tmp_path, "queued-4.wav"), AnalysisSettings())
            )
        )
        await _wait_until(lambda: queued[0].done())
        assert worker.queued_source_count == 4
        assert worker.active_worker_count <= 1
        with pytest.raises(QueueWaiterReplaced):
            await queued[0]
        assert not replaced_wav.exists()
        release_path.touch()
        await active
        for waiter in queued[1:]:
            assert (await waiter).key.status == "reliable"
        assert worker.worker_start_count == 1
    finally:
        release_path.touch()
        if not active.done():
            active.cancel()
        await worker.close()


@pytest.mark.asyncio
async def test_same_identity_coalesces(tmp_path):
    context = multiprocessing.get_context("spawn")
    release_path = tmp_path / "release"
    started = context.Event()
    worker = AnalysisWorker(
        worker_target=_fake_worker_loop,
        worker_target_args=(str(release_path), started),
    )
    first_path = _wav(tmp_path, "first.wav", b"block")
    second_path = _wav(tmp_path, "second.wav", b"different file")
    try:
        first = asyncio.create_task(worker.submit("same-identity", first_path, AnalysisSettings()))
        assert await asyncio.to_thread(started.wait, 3)
        second = asyncio.create_task(worker.submit("same-identity", second_path, AnalysisSettings()))
        await _wait_until(lambda: worker.coalesced_waiter_count == 1)
        release_path.touch()
        result_a, result_b = await asyncio.gather(first, second)
        assert result_a == result_b
        assert worker.processed_job_count == 1
        assert worker.queued_source_count == 0
    finally:
        release_path.touch()
        await worker.close()


@pytest.mark.asyncio
async def test_component_error_preserves_other_result(tmp_path):
    worker = AnalysisWorker(worker_target=_fake_worker_loop)
    try:
        result = await worker.submit(
            "component-error", _wav(tmp_path, "rhythm-error.wav", b"rhythm-error"), AnalysisSettings()
        )
        assert result.key.status == "reliable"
        assert result.rhythm.status == "failed"
        assert result.rhythm.reason == "mocked rhythm failure"
    finally:
        await worker.close()


@pytest.mark.asyncio
async def test_timeout_waits_for_child_exit_before_releasing_wav(tmp_path):
    context = multiprocessing.get_context("spawn")
    started = context.Event()
    terminating = context.Event()
    allow_exit = context.Event()
    marker = tmp_path / "wav-present-at-termination.txt"
    worker = AnalysisWorker(
        worker_target=_terminating_worker_loop,
        worker_target_args=(str(marker), started, terminating, allow_exit),
        execution_timeout=0.2,
    )
    try:
        result_task = asyncio.create_task(
            worker.submit("timeout", _wav(tmp_path, "timeout.wav"), AnalysisSettings())
        )
        assert await asyncio.to_thread(started.wait, 3)
        managed_path = worker.managed_paths["timeout"]
        assert await asyncio.to_thread(terminating.wait, 3)
        assert marker.read_text(encoding="utf-8") == "True"
        assert managed_path.is_file()
        allow_exit.set()
        result = await result_task
        assert result.key.status == "failed"
        assert result.rhythm.status == "failed"
        assert marker.read_text(encoding="utf-8") == "True"
        assert not managed_path.exists()
    finally:
        allow_exit.set()
        await worker.close()


@pytest.mark.asyncio
async def test_dead_worker_restarts_on_next_explicit_request(tmp_path):
    starts_path = tmp_path / "starts.log"

    worker = AnalysisWorker(
        worker_target=_recording_fake_worker,
        worker_target_args=(str(starts_path),),
    )
    try:
        crashed = await worker.submit("crash", _wav(tmp_path, "crash.wav", b"crash"), AnalysisSettings())
        assert crashed.key.status == "failed"
        assert starts_path.read_text(encoding="utf-8").splitlines() == ["start"]
        healthy = await worker.submit("next", _wav(tmp_path, "next.wav"), AnalysisSettings())
        assert healthy.key.status == "reliable"
        assert starts_path.read_text(encoding="utf-8").splitlines() == ["start", "start"]
        assert worker.worker_start_count == 2
        assert worker.active_worker_count == 1
    finally:
        await worker.close()


def _recording_fake_worker(command_receiver, result_sender, starts_path):
    with open(starts_path, "a", encoding="utf-8") as starts:
        starts.write("start\n")
    result_sender.send({"kind": "ready"})
    while True:
        command = command_receiver.recv()
        if command["kind"] == "stop":
            return
        payload = Path(command["wav_path"]).read_bytes()
        if payload == b"crash":
            os._exit(17)
        result_sender.send(
            {
                "kind": "result",
                "job_id": command["job_id"],
                "result": _result(command["job_id"], command["settings"]),
            }
        )
