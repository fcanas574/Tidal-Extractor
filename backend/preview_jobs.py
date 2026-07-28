from __future__ import annotations

import asyncio
import inspect
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Literal

PreviewStatus = Literal["queued", "processing", "complete", "failed"]


@dataclass(slots=True)
class PreviewMetadataSnapshot:
    track_id: int
    status: PreviewStatus
    revision: int
    waveform: dict | None = None
    key: str | None = None
    camelot: str | None = None
    bpm: float | None = None
    error: str | None = None


@dataclass(slots=True)
class _PreviewJob:
    track_id: int
    stream_url: str
    duration: float | None
    task: asyncio.Task[Any] | None
    snapshot: PreviewMetadataSnapshot


class PreviewJobManager:
    def __init__(self, analyzer: Callable[..., Any] | None = None):
        self.analyzer = analyzer or (lambda *_: {})
        self._test_loop = asyncio.new_event_loop()
        self._lock = RLock()
        self._jobs: dict[int, _PreviewJob] = {}
        self._active_track_ids: set[int] = set()

    def start_or_get(self, track_id: int, stream_url: str, duration: float | None) -> PreviewMetadataSnapshot:
        with self._lock:
            self._prune_completed_jobs_locked()

            job = self._jobs.get(track_id)
            if job is not None:
                return self._clone_snapshot(job.snapshot)

            snapshot = PreviewMetadataSnapshot(
                track_id=track_id,
                status="queued",
                revision=1,
            )
            job = _PreviewJob(
                track_id=track_id,
                stream_url=stream_url,
                duration=duration,
                task=None,
                snapshot=snapshot,
            )
            self._jobs[track_id] = job
            self._active_track_ids.add(track_id)

        loop = self._get_scheduling_loop()
        task = loop.create_task(self._run_job(track_id))
        with self._lock:
            current_job = self._jobs.get(track_id)
            if current_job is not None:
                current_job.task = task
        return self._clone_snapshot(snapshot)

    def snapshot(self, track_id: int) -> PreviewMetadataSnapshot | None:
        with self._lock:
            job = self._jobs.get(track_id)
            if job is None:
                return None
            return self._clone_snapshot(job.snapshot)

    def active_job_count(self) -> int:
        with self._lock:
            self._prune_completed_jobs_locked()
            return len(self._active_track_ids)

    def run_pending_for_test(self) -> None:
        while True:
            with self._lock:
                pending_tasks = [
                    job.task
                    for track_id in list(self._active_track_ids)
                    if (job := self._jobs.get(track_id)) is not None
                    and job.task is not None
                    and job.task.get_loop() is self._test_loop
                    and not job.task.done()
                ]
                if not pending_tasks:
                    self._prune_completed_jobs_locked()
                    return
            self._test_loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
            with self._lock:
                self._prune_completed_jobs_locked()

    def __del__(self) -> None:
        with suppress(Exception):
            self._shutdown()

    async def _run_job(self, track_id: int) -> None:
        with self._lock:
            job = self._jobs.get(track_id)
            if job is None:
                return
            self._update_snapshot_locked(job, status="processing")
        try:
            result = self.analyzer(job.stream_url, job.duration, job.track_id)
            if inspect.isawaitable(result):
                result = await result
            result_data = self._extract_result_data(result)
            with self._lock:
                current_job = self._jobs.get(track_id)
                if current_job is not None:
                    self._update_snapshot_locked(current_job, status="complete", **result_data)
        except Exception as exc:  # pragma: no cover - exercised by unit tests
            with self._lock:
                current_job = self._jobs.get(track_id)
                if current_job is not None:
                    self._update_snapshot_locked(current_job, status="failed", error=str(exc))

    def _update_snapshot_locked(self, job: _PreviewJob, **updates: Any) -> None:
        job.snapshot = PreviewMetadataSnapshot(
            track_id=job.snapshot.track_id,
            status=updates.get("status", job.snapshot.status),
            revision=job.snapshot.revision + 1,
            waveform=deepcopy(updates.get("waveform", job.snapshot.waveform)),
            key=updates.get("key", job.snapshot.key),
            camelot=updates.get("camelot", job.snapshot.camelot),
            bpm=updates.get("bpm", job.snapshot.bpm),
            error=updates.get("error", job.snapshot.error),
        )

    def _prune_completed_jobs_locked(self) -> None:
        for track_id in list(self._active_track_ids):
            job = self._jobs.get(track_id)
            if job is None or job.task is None or not job.task.done():
                continue
            self._active_track_ids.discard(track_id)

    def _shutdown(self) -> None:
        with self._lock:
            pending_tasks = [
                job.task
                for job in self._jobs.values()
                if job.task is not None and not job.task.done() and job.task.get_loop() is self._test_loop
            ]
            for task in pending_tasks:
                task.cancel()
        if pending_tasks:
            self._test_loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
        if not self._test_loop.is_closed():
            self._test_loop.close()

    def _get_scheduling_loop(self) -> asyncio.AbstractEventLoop:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return self._test_loop

    @staticmethod
    def _extract_result_data(result: Any) -> dict[str, Any]:
        if result is None:
            return {}
        if isinstance(result, dict):
            return {
                key: result.get(key)
                for key in ("waveform", "key", "camelot", "bpm")
                if key in result
            }
        return {
            key: getattr(result, key)
            for key in ("waveform", "key", "camelot", "bpm")
            if hasattr(result, key)
        }

    @staticmethod
    def _clone_snapshot(snapshot: PreviewMetadataSnapshot) -> PreviewMetadataSnapshot:
        return PreviewMetadataSnapshot(
            track_id=snapshot.track_id,
            status=snapshot.status,
            revision=snapshot.revision,
            waveform=deepcopy(snapshot.waveform),
            key=snapshot.key,
            camelot=snapshot.camelot,
            bpm=snapshot.bpm,
            error=snapshot.error,
        )
