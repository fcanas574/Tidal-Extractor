from __future__ import annotations

import asyncio
import inspect
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
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
        self._loop = asyncio.new_event_loop()
        self._lock = asyncio.Lock()
        self._jobs: dict[int, _PreviewJob] = {}
        self._active_track_ids: set[int] = set()

    def start_or_get(self, track_id: int, stream_url: str, duration: float | None) -> PreviewMetadataSnapshot:
        self._prune_completed_jobs()

        job = self._jobs.get(track_id)
        if job is not None:
            return self._clone_snapshot(job.snapshot)

        snapshot = PreviewMetadataSnapshot(
            track_id=track_id,
            status="queued",
            revision=1,
        )
        task = self._loop.create_task(self._run_job(track_id))
        self._jobs[track_id] = _PreviewJob(
            track_id=track_id,
            stream_url=stream_url,
            duration=duration,
            task=task,
            snapshot=snapshot,
        )
        self._active_track_ids.add(track_id)
        return self._clone_snapshot(snapshot)

    def snapshot(self, track_id: int) -> PreviewMetadataSnapshot | None:
        job = self._jobs.get(track_id)
        if job is None:
            return None
        return self._clone_snapshot(job.snapshot)

    def active_job_count(self) -> int:
        self._prune_completed_jobs()
        return len(self._active_track_ids)

    def run_pending_for_test(self) -> None:
        while True:
            pending_tasks = [
                job.task
                for track_id in list(self._active_track_ids)
                if (job := self._jobs.get(track_id)) is not None
                and job.task is not None
                and not job.task.done()
            ]
            if not pending_tasks:
                self._prune_completed_jobs()
                return
            self._loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
            self._prune_completed_jobs()

    def __del__(self) -> None:
        with suppress(Exception):
            self._shutdown()

    async def _run_job(self, track_id: int) -> None:
        job = self._jobs.get(track_id)
        if job is None:
            return

        await self._set_snapshot(track_id, status="processing")
        try:
            result = self.analyzer(job.stream_url, job.duration)
            if inspect.isawaitable(result):
                result = await result
            result_data = self._extract_result_data(result)
            await self._set_snapshot(track_id, status="complete", **result_data)
        except Exception as exc:  # pragma: no cover - exercised by unit tests
            await self._set_snapshot(track_id, status="failed", error=str(exc))

    async def _set_snapshot(self, track_id: int, **updates: Any) -> None:
        async with self._lock:
            job = self._jobs.get(track_id)
            if job is None:
                return
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

    def _prune_completed_jobs(self) -> None:
        for track_id in list(self._active_track_ids):
            job = self._jobs.get(track_id)
            if job is None or job.task is None or not job.task.done():
                continue
            self._active_track_ids.discard(track_id)

    def _shutdown(self) -> None:
        pending_tasks = [
            job.task
            for job in self._jobs.values()
            if job.task is not None and not job.task.done()
        ]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            self._loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
        if not self._loop.is_closed():
            self._loop.close()

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
