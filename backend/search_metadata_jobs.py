"""Coalesce visible-page catalog metadata work outside the search response path."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


logger = logging.getLogger(__name__)

EnrichTracks = Callable[[list[dict]], Awaitable[list[dict]]]
CompleteJob = Callable[[dict[str, tuple[int, ...]], list[dict]], Awaitable[None]]


@dataclass
class _PendingJob:
    subscriptions: dict[str, tuple[int, ...]]
    tracks: list[dict]
    task: asyncio.Task[None] | None


class SearchMetadataJobManager:
    """Run one provider lookup for matching visible track-ID sets."""

    def __init__(self, *, enrich: EnrichTracks, on_complete: CompleteJob):
        self._enrich = enrich
        self._on_complete = on_complete
        self._jobs: dict[tuple[int, ...], _PendingJob] = {}

    def schedule(self, cache_key: str, tracks: list[dict]) -> bool:
        """Schedule enrichment, joining an existing job for the same IDs."""
        job_key = tuple(sorted({int(track["id"]) for track in tracks}))
        if not job_key:
            return False

        expected_ids = tuple(int(track["id"]) for track in tracks)
        pending = self._jobs.get(job_key)
        if pending is not None:
            pending.subscriptions[cache_key] = expected_ids
            return True

        pending = _PendingJob(
            subscriptions={cache_key: expected_ids},
            tracks=list(tracks),
            task=None,
        )
        self._jobs[job_key] = pending
        pending.task = asyncio.create_task(self._run(job_key, pending))
        return True

    async def close(self) -> None:
        """Cancel outstanding work before application resources are released."""
        tasks = [pending.task for pending in self._jobs.values() if pending.task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._jobs.clear()

    async def _run(self, job_key: tuple[int, ...], pending: _PendingJob) -> None:
        tracks = pending.tracks
        try:
            try:
                tracks = await self._enrich(pending.tracks)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Background search metadata enrichment failed")

            try:
                await self._on_complete(dict(pending.subscriptions), tracks)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Background search metadata completion failed")
        finally:
            if self._jobs.get(job_key) is pending:
                self._jobs.pop(job_key, None)
