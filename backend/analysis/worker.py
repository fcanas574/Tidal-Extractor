"""A lazy, persistent spawned process for CPU-bound preview analysis."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import math
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Callable

from .types import (
    AnalysisSettings,
    GridResult,
    HybridAnalysisResult,
    KeyResult,
    RhythmResult,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ZERO_SHA256 = "0" * 64
_DEFAULT_MAX_WAITING = 4
_DEFAULT_TIMEOUT_SECONDS = 180.0
_STARTUP_TIMEOUT_SECONDS = 30.0
_STOP_GRACE_SECONDS = 1.0


class QueueWaiterReplaced(RuntimeError):
    """Raised when bounded queue pressure replaces the oldest waiting source."""


class AnalysisWorkerClosed(RuntimeError):
    """Raised when a request is submitted after the worker has closed."""


@dataclass
class _PendingJob:
    job_id: str
    wav_path: Path
    settings: AnalysisSettings
    waiters: list[asyncio.Future[HybridAnalysisResult]]


def _failure_result(
    job_id: str,
    settings: AnalysisSettings,
    reason: str,
    *,
    duration_seconds: float = 0.0,
) -> HybridAnalysisResult:
    """Return structured component failures for a process-level failure."""
    fingerprint = job_id.lower() if _SHA256_RE.fullmatch(job_id) else hashlib.sha256(
        job_id.encode("utf-8")
    ).hexdigest()
    if not math.isfinite(duration_seconds) or duration_seconds < 0:
        duration_seconds = 0.0
    grid = GridResult(
        bpm=None,
        period_seconds=None,
        origin_seconds=None,
        meter=None,
        first_downbeat_beat=None,
        status="failed",
        residual_p95_seconds=None,
        split_drift_seconds=None,
        reason=reason,
    )
    return HybridAnalysisResult(
        schema_version=settings.schema_version,
        audio_fingerprint=fingerprint,
        decoder_version="",
        duration_seconds=duration_seconds,
        model_id=settings.model_id,
        model_sha256=_ZERO_SHA256,
        key_profile_id=settings.key_profile_id,
        settings_sha256=settings.sha256,
        key=KeyResult(
            key=None,
            camelot=None,
            status="failed",
            candidates=(),
            agreement=None,
            reason=reason,
        ),
        rhythm=RhythmResult(
            bpm=None,
            beats=(),
            downbeats=(),
            grid=grid,
            status="failed",
            reason=reason,
        ),
    )


def _configure_child_threads() -> Any:
    """Limit numerical libraries before importing any inference dependencies."""
    for variable in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        os.environ[variable] = "2"

    from threadpoolctl import threadpool_limits

    limits = threadpool_limits(limits=2)
    return limits


def _load_model_once(rhythm_engine: Any, model_id: str, cache: dict[str, dict[str, Any]]):
    """Load the verified local checkpoint once in this child process."""
    if model_id in cache:
        return cache[model_id]

    entry: dict[str, Any] = {
        "path": None,
        "sha256": _ZERO_SHA256,
        "model": None,
        "error": None,
        "error_status": "failed",
    }
    try:
        model_path = rhythm_engine.get_model_path(model_id)
        model_sha256 = rhythm_engine._checkpoint_sha256(Path(model_path))
        entry["path"] = Path(model_path)
        entry["sha256"] = model_sha256
        import torch

        torch.set_num_threads(2)
        try:
            torch.set_num_interop_threads(2)
        except RuntimeError:
            if torch.get_num_interop_threads() != 2:
                raise
        file2beats = rhythm_engine._load_file2beats()(
            checkpoint_path=str(model_path), device="cpu", dbn=False
        )
        entry["model"] = file2beats
    except FileNotFoundError as exc:
        entry["error"] = f"beat model unavailable: {exc}"
        entry["error_status"] = "unavailable"
    except Exception as exc:
        entry["error"] = f"beat model unavailable: {exc}"
    else:
        cache[model_id] = entry
    return entry


def _failed_rhythm(reason: str) -> RhythmResult:
    grid = GridResult(
        bpm=None,
        period_seconds=None,
        origin_seconds=None,
        meter=None,
        first_downbeat_beat=None,
        status="failed",
        residual_p95_seconds=None,
        split_drift_seconds=None,
        reason=reason,
    )
    return RhythmResult(
        bpm=None,
        beats=(),
        downbeats=(),
        grid=grid,
        status="failed",
        reason=reason,
    )


def _unavailable_rhythm(reason: str) -> RhythmResult:
    grid = GridResult(
        bpm=None,
        period_seconds=None,
        origin_seconds=None,
        meter=None,
        first_downbeat_beat=None,
        status="unavailable",
        residual_p95_seconds=None,
        split_drift_seconds=None,
        reason=reason,
    )
    return RhythmResult(
        bpm=None,
        beats=(),
        downbeats=(),
        grid=grid,
        status="unavailable",
        reason=reason,
    )


def _analyze_in_child(
    job_id: str,
    wav_path: str,
    settings: AnalysisSettings,
    model_cache: dict[str, dict[str, Any]],
) -> HybridAnalysisResult:
    """Run both components independently and keep either successful result."""
    import numpy as np
    import soundfile as sf

    from . import key_engine, rhythm_engine

    audio_path = Path(wav_path)
    try:
        pcm, sample_rate = sf.read(audio_path, dtype="float32", always_2d=False)
        pcm = np.asarray(pcm, dtype=np.float32)
        if pcm.ndim == 2:
            pcm = np.mean(pcm, axis=1, dtype=np.float32)
        elif pcm.ndim != 1:
            raise ValueError("decoded WAV must contain mono or stereo PCM")
        duration_seconds = float(pcm.size / sample_rate) if sample_rate else 0.0
    except Exception as exc:
        reason = f"could not read decoded WAV: {exc}"
        return _failure_result(job_id, settings, reason)

    model = _load_model_once(rhythm_engine, settings.model_id, model_cache)
    model_path = model["path"] or audio_path
    model_sha256 = model["sha256"]

    if model["error"]:
        if model["error_status"] == "unavailable":
            rhythm = _unavailable_rhythm(model["error"])
        else:
            rhythm = _failed_rhythm(model["error"])
    else:
        loaded_instance = model["model"]
        # Task 3 verifies the checkpoint for each analysis. Its lazy class loader
        # is wrapped so the verified model object itself is reused by this child.
        rhythm_engine._load_file2beats = lambda: (
            lambda **_kwargs: loaded_instance
        )

        try:
            rhythm = rhythm_engine.estimate_rhythm(
                str(audio_path),
                duration_seconds,
                Path(model_path),
                settings.model_id,
                model_sha256,
                settings,
            )
        except Exception as exc:
            rhythm = _failed_rhythm(f"rhythm analysis failed: {exc}")

    try:
        key = key_engine.estimate_key(pcm, int(sample_rate), rhythm, duration_seconds)
    except Exception as exc:
        key = KeyResult(
            key=None,
            camelot=None,
            status="failed",
            candidates=(),
            agreement=None,
            reason=f"key analysis failed: {exc}",
        )

    fingerprint = job_id.lower() if _SHA256_RE.fullmatch(job_id) else hashlib.sha256(
        job_id.encode("utf-8")
    ).hexdigest()
    return HybridAnalysisResult(
        schema_version=settings.schema_version,
        audio_fingerprint=fingerprint,
        decoder_version="",
        duration_seconds=duration_seconds,
        model_id=settings.model_id,
        model_sha256=model_sha256,
        key_profile_id=settings.key_profile_id,
        settings_sha256=settings.sha256,
        key=key,
        rhythm=rhythm,
    )


def _analysis_process_main(command_receiver, result_sender) -> None:
    """Spawn target. Imports numerical and model packages only in this child."""
    try:
        _thread_limits = _configure_child_threads()
        import numpy  # noqa: F401  (imported only after limiting child threads)

        from . import key_engine, rhythm_engine

        # Keep references alive for the life of this worker process.
        _engine_modules = (key_engine, rhythm_engine, _thread_limits)
    except Exception as exc:
        try:
            result_sender.send({"kind": "startup_error", "error": str(exc)})
        finally:
            return

    model_cache: dict[str, dict[str, Any]] = {}
    result_sender.send({"kind": "ready"})
    while True:
        try:
            command = command_receiver.recv()
        except (EOFError, OSError):
            return
        if command.get("kind") == "stop":
            return
        job_id = str(command.get("job_id", ""))
        settings = command.get("settings")
        try:
            if not isinstance(settings, AnalysisSettings):
                raise ValueError("worker received invalid analysis settings")
            result = _analyze_in_child(
                job_id,
                str(command["wav_path"]),
                settings,
                model_cache,
            )
            result_sender.send(
                {"kind": "result", "job_id": job_id, "result": result}
            )
        except BaseException as exc:
            if isinstance(settings, AnalysisSettings):
                result = _failure_result(job_id, settings, f"analysis worker failed: {exc}")
                try:
                    result_sender.send(
                        {"kind": "result", "job_id": job_id, "result": result}
                    )
                except (BrokenPipeError, EOFError, OSError):
                    return
            else:
                try:
                    result_sender.send(
                        {"kind": "error", "job_id": job_id, "error": str(exc)}
                    )
                except (BrokenPipeError, EOFError, OSError):
                    return


class AnalysisWorker:
    """One lazy spawned process with coalescing and a bounded waiting queue."""

    def __init__(
        self,
        *,
        max_waiting: int = _DEFAULT_MAX_WAITING,
        execution_timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        startup_timeout: float = _STARTUP_TIMEOUT_SECONDS,
        worker_target: Callable[..., None] = _analysis_process_main,
        worker_target_args: tuple[Any, ...] = (),
        mp_context=None,
    ) -> None:
        if isinstance(max_waiting, bool) or not isinstance(max_waiting, int) or max_waiting < 1:
            raise ValueError("max_waiting must be a positive integer")
        if max_waiting > _DEFAULT_MAX_WAITING:
            raise ValueError(f"max_waiting cannot exceed {_DEFAULT_MAX_WAITING}")
        if not math.isfinite(execution_timeout) or execution_timeout <= 0:
            raise ValueError("execution_timeout must be finite and positive")
        if execution_timeout > _DEFAULT_TIMEOUT_SECONDS:
            raise ValueError("execution_timeout cannot exceed 180 seconds")
        if not math.isfinite(startup_timeout) or startup_timeout <= 0:
            raise ValueError("startup_timeout must be finite and positive")
        self.max_waiting = max_waiting
        self.execution_timeout = float(execution_timeout)
        self.startup_timeout = float(startup_timeout)
        self._worker_target = worker_target
        self._worker_target_args = worker_target_args
        self._context = mp_context or multiprocessing.get_context("spawn")
        self._queue: OrderedDict[str, _PendingJob] = OrderedDict()
        self._jobs: dict[str, _PendingJob] = {}
        self._active_job: _PendingJob | None = None
        self._state_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._dispose_lock = asyncio.Lock()
        self._dispatcher: asyncio.Task[None] | None = None
        self._closed = False
        self._process = None
        self._command_sender = None
        self._result_receiver = None
        self._worker_start_count = 0
        self._processed_job_count = 0
        self._coalesced_waiter_count = 0
        self.managed_paths: dict[str, Path] = {}

    @property
    def active_worker_count(self) -> int:
        try:
            return int(self._process is not None and self._process.is_alive())
        except ValueError:
            # A concurrently closing process can be closed between reads.
            return 0

    @property
    def worker_start_count(self) -> int:
        return self._worker_start_count

    @property
    def processed_job_count(self) -> int:
        return self._processed_job_count

    @property
    def coalesced_waiter_count(self) -> int:
        return self._coalesced_waiter_count

    @property
    def queued_source_count(self) -> int:
        return len(self._queue)

    @property
    def process(self):
        return self._process

    @staticmethod
    def _copy_wav(source_path: Path) -> Path:
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(source)
        descriptor, temporary_name = tempfile.mkstemp(prefix="tidal-analysis-", suffix=".wav")
        os.close(descriptor)
        destination = Path(temporary_name)
        try:
            shutil.copyfile(source, destination)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return destination

    @staticmethod
    def _remove_managed_file(path: Path) -> None:
        Path(path).unlink(missing_ok=True)

    @staticmethod
    def _receive_with_timeout(connection, timeout: float):
        try:
            if not connection.poll(timeout):
                return None
            return connection.recv()
        except (EOFError, OSError):
            return None

    async def start(self) -> None:
        """Start and handshake with the child; normal callers use submit()."""
        if self._closed:
            raise AnalysisWorkerClosed("analysis worker is closed")
        async with self._start_lock:
            if self._closed:
                raise AnalysisWorkerClosed("analysis worker is closed")
            if self._process is not None and self._process.is_alive():
                return
            if self._process is not None:
                await self._dispose_process()

            command_receiver, command_sender = self._context.Pipe(duplex=False)
            result_receiver, result_sender = self._context.Pipe(duplex=False)
            process = self._context.Process(
                target=self._worker_target,
                args=(command_receiver, result_sender, *self._worker_target_args),
                name="tidal-preview-analysis",
                daemon=True,
            )
            try:
                await asyncio.to_thread(process.start)
            except BaseException:
                command_receiver.close()
                command_sender.close()
                result_receiver.close()
                result_sender.close()
                raise
            command_receiver.close()
            result_sender.close()
            self._process = process
            self._command_sender = command_sender
            self._result_receiver = result_receiver
            self._worker_start_count += 1
            message = await asyncio.to_thread(
                self._receive_with_timeout, result_receiver, self.startup_timeout
            )
            if not isinstance(message, dict) or message.get("kind") != "ready":
                error = (
                    message.get("error", "analysis worker failed its readiness handshake")
                    if isinstance(message, dict)
                    else "analysis worker failed its readiness handshake"
                )
                await self._dispose_process()
                raise RuntimeError(error)

    async def submit(
        self, job_id: str, wav_path: Path, settings: AnalysisSettings
    ) -> HybridAnalysisResult:
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("job_id must be a non-empty string")
        if not isinstance(settings, AnalysisSettings):
            raise TypeError("settings must be AnalysisSettings")
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[HybridAnalysisResult] = loop.create_future()

        async with self._state_lock:
            if self._closed:
                raise AnalysisWorkerClosed("analysis worker is closed")
            existing = self._jobs.get(job_id)
            if existing is not None:
                existing.waiters.append(waiter)
                self._coalesced_waiter_count += 1
            else:
                copy_task = asyncio.create_task(
                    asyncio.to_thread(self._copy_wav, Path(wav_path))
                )
                try:
                    managed_path = await asyncio.shield(copy_task)
                except asyncio.CancelledError as cancelled:
                    try:
                        managed_path = await copy_task
                    except BaseException:
                        raise cancelled
                    remove_task = asyncio.create_task(
                        asyncio.to_thread(self._remove_managed_file, managed_path)
                    )
                    try:
                        await asyncio.shield(remove_task)
                    finally:
                        raise cancelled
                self.managed_paths[job_id] = managed_path
                if len(self._queue) >= self.max_waiting:
                    oldest_id, oldest = self._queue.popitem(last=False)
                    self._jobs.pop(oldest_id, None)
                    self.managed_paths.pop(oldest_id, None)
                    for old_waiter in oldest.waiters:
                        if not old_waiter.done():
                            old_waiter.set_exception(
                                QueueWaiterReplaced(
                                    f"queued analysis {oldest_id!r} was replaced by newer work"
                                )
                            )
                    cleanup_task = asyncio.create_task(
                        asyncio.to_thread(self._remove_managed_file, oldest.wav_path)
                    )
                    try:
                        await asyncio.shield(cleanup_task)
                    except asyncio.CancelledError as cancelled:
                        self.managed_paths.pop(job_id, None)
                        remove_task = asyncio.create_task(
                            asyncio.to_thread(self._remove_managed_file, managed_path)
                        )
                        try:
                            await asyncio.shield(remove_task)
                        finally:
                            raise cancelled
                pending = _PendingJob(job_id, managed_path, settings, [waiter])
                self._queue[job_id] = pending
                self._jobs[job_id] = pending
                if self._dispatcher is None or self._dispatcher.done():
                    self._dispatcher = asyncio.create_task(self._dispatch())

        return await waiter

    async def _dispatch(self) -> None:
        while True:
            async with self._state_lock:
                if self._closed or not self._queue:
                    stale_paths = self._fail_waiting_jobs(
                        AnalysisWorkerClosed("analysis worker is closing")
                    )
                    pending = None
                else:
                    stale_paths = []
                    _job_id, pending = self._queue.popitem(last=False)
                    self._active_job = pending

            if pending is None:
                await asyncio.gather(
                    *(asyncio.to_thread(self._remove_managed_file, path) for path in stale_paths)
                )
                return

            try:
                result = await self._run_job(pending)
            except Exception as exc:
                result = _failure_result(pending.job_id, pending.settings, f"analysis worker failed: {exc}")
                await self._dispose_process()
            finally:
                # _run_job handles process termination on timeout/death before
                # returning. A normal result means the child finished reading.
                await asyncio.to_thread(self._remove_managed_file, pending.wav_path)
                self.managed_paths.pop(pending.job_id, None)

            async with self._state_lock:
                self._jobs.pop(pending.job_id, None)
                self._active_job = None
                waiters = tuple(pending.waiters)
            for waiter in waiters:
                if not waiter.done():
                    waiter.set_result(result)

    async def _run_job(self, pending: _PendingJob) -> HybridAnalysisResult:
        try:
            await self.start()
        except Exception as exc:
            await self._dispose_process()
            return _failure_result(pending.job_id, pending.settings, f"worker startup failed: {exc}")

        process = self._process
        command_sender = self._command_sender
        result_receiver = self._result_receiver
        if process is None or command_sender is None or result_receiver is None:
            return _failure_result(pending.job_id, pending.settings, "analysis worker is unavailable")

        try:
            async with self._state_lock:
                if self._closed:
                    return _failure_result(
                        pending.job_id,
                        pending.settings,
                        "analysis worker is closing",
                    )
                await asyncio.to_thread(
                    command_sender.send,
                    {
                        "kind": "analyze",
                        "job_id": pending.job_id,
                        "wav_path": str(pending.wav_path),
                        "settings": pending.settings,
                    },
                )
                self._processed_job_count += 1
            message = await asyncio.to_thread(
                self._receive_with_timeout, result_receiver, self.execution_timeout
            )
        except Exception as exc:
            message = None
            reason = f"analysis worker communication failed: {exc}"
        else:
            reason = ""

        if message is None:
            if process.is_alive():
                reason = "analysis worker timed out" if not reason else reason
            else:
                reason = "analysis worker exited unexpectedly"
            await self._dispose_process()
            return _failure_result(pending.job_id, pending.settings, reason)

        if (
            not isinstance(message, dict)
            or message.get("kind") != "result"
            or message.get("job_id") != pending.job_id
            or not isinstance(message.get("result"), HybridAnalysisResult)
        ):
            await self._dispose_process()
            reason = (
                str(message.get("error", "analysis worker returned an invalid response"))
                if isinstance(message, dict)
                else "analysis worker returned an invalid response"
            )
            return _failure_result(pending.job_id, pending.settings, reason)
        return message["result"]

    def _fail_waiting_jobs(self, error: Exception) -> list[Path]:
        paths = []
        while self._queue:
            job_id, pending = self._queue.popitem(last=False)
            self._jobs.pop(job_id, None)
            self.managed_paths.pop(job_id, None)
            paths.append(pending.wav_path)
            for waiter in pending.waiters:
                if not waiter.done():
                    waiter.set_exception(type(error)(str(error)))
        return paths

    @staticmethod
    def _terminate_and_join(process) -> None:
        if process.is_alive():
            process.terminate()
            process.join(_STOP_GRACE_SECONDS)
        if process.is_alive():
            process.kill()
        process.join()

    async def _dispose_process(self) -> None:
        async with self._dispose_lock:
            process = self._process
            if process is None:
                return
            command_sender = self._command_sender
            result_receiver = self._result_receiver
            await asyncio.to_thread(self._terminate_and_join, process)
            for connection in (command_sender, result_receiver):
                if connection is not None:
                    try:
                        connection.close()
                    except OSError:
                        pass
            try:
                process.close()
            except (ValueError, OSError):
                pass
            if self._process is process:
                self._process = None
                self._command_sender = None
                self._result_receiver = None

    async def close(self) -> None:
        """Stop the child and wait for confirmed exit before releasing WAVs."""
        async with self._state_lock:
            if self._closed:
                dispatcher = self._dispatcher
                stale_paths = []
            else:
                self._closed = True
                stale_paths = self._fail_waiting_jobs(
                    AnalysisWorkerClosed("analysis worker is closing")
                )
                dispatcher = self._dispatcher

        await asyncio.gather(
            *(asyncio.to_thread(self._remove_managed_file, path) for path in stale_paths)
        )

        # Serialize shutdown with spawn and its readiness handshake. This also
        # catches a process that start() has launched but not published yet.
        async with self._start_lock:
            await self._dispose_process()
        if dispatcher is not None and dispatcher is not asyncio.current_task():
            await dispatcher
        if self._process is not None:
            await self._dispose_process()
