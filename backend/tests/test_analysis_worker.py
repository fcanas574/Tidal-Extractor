import asyncio
from datetime import datetime, timezone
import hashlib
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import threading
import time
from types import ModuleType
from dataclasses import replace

import pytest

from backend.analysis.types import (
    AnalysisSettings,
    GridResult,
    HybridAnalysisResult,
    KeyCandidate,
    KeyResult,
    RhythmResult,
)
from backend.analysis.worker import (
    AnalysisWorker,
    QueueWaiterReplaced,
    _analyze_in_child,
    _load_model_once,
)


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


def test_failed_model_load_can_be_retried_after_setup_is_repaired(monkeypatch):
    class RhythmEngine:
        attempts = 0
        loaded_model = object()

        def get_model_path(self, _model_id):
            self.attempts += 1
            if self.attempts == 1:
                raise FileNotFoundError("checkpoint missing")
            return Path("/verified/final0.ckpt")

        @staticmethod
        def _checkpoint_sha256(_path):
            return "b" * 64

        def _load_file2beats(self):
            return lambda **_kwargs: self.loaded_model

    torch = ModuleType("torch")
    torch.set_num_threads = lambda _count: None
    torch.set_num_interop_threads = lambda _count: None
    torch.get_num_interop_threads = lambda: 2
    monkeypatch.setitem(sys.modules, "torch", torch)

    rhythm_engine = RhythmEngine()
    cache = {}
    failed = _load_model_once(rhythm_engine, "final0", cache)
    recovered = _load_model_once(rhythm_engine, "final0", cache)

    assert failed["error_status"] == "unavailable"
    assert recovered["error"] is None
    assert recovered["model"] is rhythm_engine.loaded_model
    assert rhythm_engine.attempts == 2


def test_worker_retry_skips_cached_successful_key_component(monkeypatch, tmp_path):
    import numpy as np

    from backend.analysis import key_engine, rhythm_engine

    settings = AnalysisSettings()
    job_id = "d" * 64
    previous = _result(job_id, settings)
    recomputed_rhythm = replace(
        previous.rhythm,
        status="needs_review",
        reason="recomputed rhythm needs review",
        grid=replace(
            previous.rhythm.grid,
            status="needs_review",
            reason="recomputed rhythm needs review",
        ),
    )
    soundfile = ModuleType("soundfile")
    soundfile.read = lambda *_args, **_kwargs: (
        np.zeros(44_100, dtype=np.float32),
        44_100,
    )
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)
    monkeypatch.setattr(
        "backend.analysis.worker._load_model_once",
        lambda *_args: {
            "path": tmp_path / "model.ckpt",
            "sha256": "b" * 64,
            "model": object(),
            "error": None,
            "error_status": "failed",
        },
    )
    rhythm_calls = []
    monkeypatch.setattr(
        rhythm_engine,
        "estimate_rhythm",
        lambda *args: rhythm_calls.append(args) or recomputed_rhythm,
    )
    key_calls = []

    def estimate_key(*_args):
        key_calls.append(True)
        raise AssertionError("cached successful key must not be recomputed")

    monkeypatch.setattr(key_engine, "estimate_key", estimate_key)

    result = _analyze_in_child(
        job_id,
        str(tmp_path / "preview.wav"),
        settings,
        {},
        components=frozenset({"rhythm"}),
        prior_result=previous,
    )

    assert result.key == previous.key
    assert result.rhythm == recomputed_rhythm
    assert rhythm_calls
    assert key_calls == []


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
async def test_close_during_startup_does_not_launch_queued_job(tmp_path):
    context = multiprocessing.get_context("spawn")
    worker = AnalysisWorker(worker_target=_fake_worker_loop, mp_context=context)
    start_entered = threading.Event()
    release_start = threading.Event()
    real_process_factory = context.Process

    class BlockingStartContext:
        Pipe = staticmethod(context.Pipe)

        class DelayedProcess:
            def __init__(self, process):
                self.process = process

            def start(self):
                start_entered.set()
                if not release_start.wait(3):
                    raise TimeoutError("test did not release process startup")
                self.process.start()

            def __getattr__(self, name):
                return getattr(self.process, name)

        @staticmethod
        def Process(**kwargs):
            process = real_process_factory(**kwargs)
            return BlockingStartContext.DelayedProcess(process)

    worker._context = BlockingStartContext()
    submitter = asyncio.create_task(
        worker.submit("closing-race", _wav(tmp_path, "startup-race.wav"), AnalysisSettings())
    )
    closer = None
    try:
        assert await asyncio.to_thread(start_entered.wait, 3)
        closer = asyncio.create_task(worker.close())
        await _wait_until(lambda: worker._closed)
        assert not closer.done()
        release_start.set()

        result = await submitter
        await closer

        assert result.key.status == "failed"
        assert worker.processed_job_count == 0
        assert worker.process is None
        assert worker.active_worker_count == 0
    finally:
        release_start.set()
        if not submitter.done():
            submitter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await submitter
        if closer is not None:
            await closer


@pytest.mark.asyncio
async def test_cancellation_during_wav_copy_removes_completed_managed_file(tmp_path, monkeypatch):
    worker = AnalysisWorker(worker_target=_fake_worker_loop)
    copy_started = threading.Event()
    release_copy = threading.Event()
    copy_finished = threading.Event()
    copied_paths = []
    real_copy = worker._copy_wav

    def delayed_copy(source_path):
        copy_started.set()
        if not release_copy.wait(3):
            raise TimeoutError("test did not release WAV copy")
        path = real_copy(source_path)
        copied_paths.append(path)
        copy_finished.set()
        return path

    monkeypatch.setattr(worker, "_copy_wav", delayed_copy)
    submitter = asyncio.create_task(
        worker.submit("cancel-copy", _wav(tmp_path, "cancel-copy.wav"), AnalysisSettings())
    )
    try:
        assert await asyncio.to_thread(copy_started.wait, 3)
        submitter.cancel()
        await asyncio.sleep(0.05)
        release_copy.set()
        with pytest.raises(asyncio.CancelledError):
            await submitter

        assert await asyncio.to_thread(copy_finished.wait, 3)
        assert len(copied_paths) == 1
        assert not copied_paths[0].exists()
    finally:
        release_copy.set()
        if not submitter.done():
            submitter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await submitter
        for path in copied_paths:
            path.unlink(missing_ok=True)
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
async def test_cancel_during_eviction_cleanup_removes_new_wav_and_notifies_evicted_waiter(
    tmp_path, monkeypatch
):
    context = multiprocessing.get_context("spawn")
    release_path = tmp_path / "release"
    started = context.Event()
    worker = AnalysisWorker(
        worker_target=_fake_worker_loop,
        worker_target_args=(str(release_path), started),
        max_waiting=4,
    )
    active = asyncio.create_task(
        worker.submit(
            "active", _wav(tmp_path, "active.wav", b"block"), AnalysisSettings()
        )
    )
    queued = []
    submitter = None
    release_cleanup = threading.Event()
    cleanup_started = threading.Event()
    cleanup_finished = threading.Event()
    copied_paths = []
    real_copy = worker._copy_wav
    real_remove = worker._remove_managed_file

    def record_copy(source_path):
        path = real_copy(source_path)
        copied_paths.append(path)
        return path

    monkeypatch.setattr(worker, "_copy_wav", record_copy)
    try:
        assert await asyncio.to_thread(started.wait, 3)
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

        evicted_path = worker.managed_paths["queued-0"]

        def block_evicted_cleanup(path):
            if Path(path) == evicted_path:
                cleanup_started.set()
                if not release_cleanup.wait(3):
                    raise TimeoutError("test did not release eviction cleanup")
                result = real_remove(path)
                cleanup_finished.set()
                return result
            return real_remove(path)

        monkeypatch.setattr(worker, "_remove_managed_file", block_evicted_cleanup)
        submitter = asyncio.create_task(
            worker.submit(
                "cancelled-fifth",
                _wav(tmp_path, "cancelled-fifth.wav"),
                AnalysisSettings(),
            )
        )
        assert await asyncio.to_thread(cleanup_started.wait, 3)
        assert len(copied_paths) == 6
        new_managed_path = copied_paths[-1]
        assert new_managed_path.is_file()

        submitter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await submitter
        release_cleanup.set()
        assert await asyncio.to_thread(cleanup_finished.wait, 3)

        assert not new_managed_path.exists()
        assert queued[0].done()
        with pytest.raises(QueueWaiterReplaced):
            await queued[0]
        assert worker.queued_source_count == 3
        assert set(worker.managed_paths) == set(worker._jobs)
        assert set(worker.managed_paths) == {
            "active",
            "queued-1",
            "queued-2",
            "queued-3",
        }

        release_path.touch()
        assert (await active).key.status == "reliable"
        for waiter in queued[1:]:
            assert (await waiter).key.status == "reliable"
    finally:
        release_cleanup.set()
        release_path.touch()
        if submitter is not None and not submitter.done():
            submitter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await submitter
        await worker.close()
        for waiter in (active, *queued):
            if not waiter.done():
                waiter.cancel()
        await asyncio.gather(active, *queued, return_exceptions=True)
        for path in copied_paths:
            path.unlink(missing_ok=True)


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
