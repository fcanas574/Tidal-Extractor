from __future__ import annotations

import asyncio
import inspect
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Callable, Literal
from urllib.parse import urlsplit, urlunsplit

PreviewStatus = Literal["queued", "processing", "partial", "complete", "failed"]
_SNAPSHOT_ALIAS_TTL = timedelta(hours=24)
_MAX_RETAINED_SNAPSHOTS = 256
_MAX_INFLIGHT_JOBS = 5  # one active source plus four waiting sources


class PreviewJobQueueFullError(RuntimeError):
    """The preview worker and its four waiting slots are occupied."""


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
    waveform_status: Literal["queued", "processing", "complete", "failed"] = "queued"
    analysis_status: Literal["queued", "processing", "complete", "failed", "unknown", "deferred"] = "queued"
    analysis: dict | None = None
    analysis_error: str | None = None
    key_source: Literal["local", "provider"] | None = None
    bpm_source: Literal["local", "provider"] | None = None
    provider_key: str | None = None
    provider_camelot: str | None = None
    provider_bpm: float | None = None


@dataclass(slots=True)
class _PreviewJob:
    track_id: int
    stream_url: str
    duration: float | None
    task: asyncio.Task[Any] | None
    snapshot: PreviewMetadataSnapshot
    identity: tuple[str, str, float | None, str | None, str | None]
    completed_at_utc: datetime | None = None


class PreviewJobManager:
    def __init__(
        self,
        analyzer: Callable[..., Any] | None = None,
        analysis_retry: Callable[..., Any] | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        snapshot_ttl: timedelta = _SNAPSHOT_ALIAS_TTL,
        max_retained_snapshots: int = _MAX_RETAINED_SNAPSHOTS,
    ):
        self.analyzer = analyzer or (lambda *_: {})
        self.analysis_retry = analysis_retry
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._snapshot_ttl = snapshot_ttl
        self._max_retained_snapshots = max_retained_snapshots
        self._test_loop = asyncio.new_event_loop()
        self._lock = RLock()
        self._jobs: dict[int, _PreviewJob] = {}
        self._retired_jobs: list[_PreviewJob] = []

    def start_or_get(
        self,
        track_id: int,
        stream_url: str,
        duration: float | None,
        *,
        preview_profile: str = "LOW",
        decoder_version: str | None = None,
        settings_identity: str | None = None,
    ) -> PreviewMetadataSnapshot:
        with self._lock:
            self._prune_completed_jobs_locked()

            job = self._jobs.get(track_id)
            if job is not None:
                identity = self._preview_identity(
                    stream_url,
                    duration,
                    preview_profile,
                    decoder_version,
                    settings_identity,
                )
                if job.identity == identity and self._is_current_alias_locked(job):
                    return self._clone_snapshot(job.snapshot)

            identity = self._preview_identity(
                stream_url,
                duration,
                preview_profile,
                decoder_version,
                settings_identity,
            )
            if self._inflight_job_count_locked() >= _MAX_INFLIGHT_JOBS:
                raise PreviewJobQueueFullError(
                    "preview job capacity reached (one active source plus four waiting sources)"
                )

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
                identity=identity,
            )
            loop = self._get_scheduling_loop()
            job.task = self._create_job_task(loop, job)
            current_job = self._jobs.get(track_id)
            if (
                current_job is not None
                and current_job.task is not None
                and not current_job.task.done()
            ):
                self._retired_jobs.append(current_job)
            self._jobs[track_id] = job
            return self._clone_snapshot(snapshot)

    def snapshot(self, track_id: int) -> PreviewMetadataSnapshot | None:
        with self._lock:
            self._prune_completed_jobs_locked()
            job = self._jobs.get(track_id)
            if job is None:
                return None
            return self._clone_snapshot(job.snapshot)

    def active_job_count(self) -> int:
        with self._lock:
            self._prune_completed_jobs_locked()
            return self._inflight_job_count_locked()

    def run_pending_for_test(self) -> None:
        while True:
            with self._lock:
                pending_tasks = [
                    job.task
                    for job in (*self._jobs.values(), *self._retired_jobs)
                    if job.task is not None
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

    async def _run_job(self, job: _PreviewJob, *, retry: bool = False) -> None:
        track_id = job.track_id
        with self._lock:
            if self._jobs.get(track_id) is not job:
                return
            updates = {"status": "processing"}
            if retry:
                updates.update(analysis_status="processing", analysis_error=None, error=None)
            self._update_snapshot_locked(job, **updates)

        # Create a progressive snapshot callback that the analyzer can call
        # to publish intermediate waveform data before the final result arrives.
        async def _on_progress(snapshot: dict) -> None:
            with self._lock:
                current_job = self._jobs.get(track_id)
                if current_job is job:
                    progress: dict[str, Any] = {}
                    bands = snapshot.get("bands")
                    duration = snapshot.get("duration")
                    waveform = snapshot.get("waveform")
                    if waveform is None and bands is not None:
                        # Wrap bands in the frontend WaveformData contract:
                        # { bands: {low,mid,high}, duration }.
                        waveform = {"bands": bands, "duration": duration}
                    if waveform is not None:
                        progress["waveform"] = waveform
                        if "complete" in snapshot:
                            progress["waveform_status"] = (
                                "complete"
                                if snapshot["complete"] and _waveform_is_usable(waveform)
                                else "processing" if not snapshot["complete"] else "failed"
                            )
                            if snapshot["complete"] and "analysis_status" not in snapshot:
                                progress["analysis_status"] = "processing"
                    for name in (
                        "analysis_status",
                        "analysis",
                        "analysis_error",
                        "provider_key",
                        "provider_camelot",
                        "provider_bpm",
                        "key",
                        "camelot",
                        "bpm",
                        "key_source",
                        "bpm_source",
                    ):
                        if name in snapshot:
                            progress[name] = snapshot[name]
                    if progress:
                        self._update_snapshot_locked(current_job, **progress)

        try:
            if retry:
                if self.analysis_retry is None:
                    raise RuntimeError("preview analysis retry is unavailable")
                result = self.analysis_retry(job.stream_url, job.duration, job.track_id)
            else:
                result = self.analyzer(
                    job.stream_url, job.duration, job.track_id,
                    on_snapshot=_on_progress,
                )
            if inspect.isawaitable(result):
                result = await result
            result_data = self._extract_result_data(result)
            with self._lock:
                current_job = self._jobs.get(track_id)
                if current_job is job:
                    updates = dict(result_data)
                    if "analysis_status" not in updates:
                        updates["analysis_status"] = "complete"
                    if "waveform" in updates:
                        updates.setdefault(
                            "waveform_status",
                            "complete" if _waveform_is_usable(updates["waveform"]) else "failed",
                        )
                    elif current_job.snapshot.waveform_status == "queued":
                        # Preserve older analyzers which only provide metadata.
                        updates["waveform_status"] = "complete"
                    self._update_snapshot_locked(current_job, **updates)
        except Exception as exc:  # pragma: no cover - exercised by unit tests
            with self._lock:
                current_job = self._jobs.get(track_id)
                if current_job is job:
                    waveform_status = current_job.snapshot.waveform_status
                    self._update_snapshot_locked(
                        current_job,
                        waveform_status=waveform_status,
                        analysis_status="failed",
                        analysis_error=str(exc),
                        error=str(exc),
                    )
        finally:
            with self._lock:
                job.completed_at_utc = self._now_utc()

    def publish_progress(self, track_id: int, updates: dict) -> None:
        """Merge partial fields into the live snapshot with a revision bump."""
        with self._lock:
            job = self._jobs.get(track_id)
            if job is None:
                return
            merged = {
                key: updates[key]
                for key in (
                    "waveform",
                    "waveform_status",
                    "analysis_status",
                    "analysis",
                    "analysis_error",
                    "provider_key",
                    "provider_camelot",
                    "provider_bpm",
                    "key",
                    "camelot",
                    "bpm",
                    "key_source",
                    "bpm_source",
                )
                if key in updates
            }
            if "waveform" in merged and "waveform_status" not in merged:
                merged["waveform_status"] = (
                    "complete" if _waveform_is_usable(merged["waveform"]) else "processing"
                )
            self._update_snapshot_locked(job, **merged)

    def _update_snapshot_locked(self, job: _PreviewJob, **updates: Any) -> None:
        previous = job.snapshot
        analysis = deepcopy(updates.get("analysis", previous.analysis))
        provider_key = updates.get("provider_key", previous.provider_key)
        provider_camelot = updates.get("provider_camelot", previous.provider_camelot)
        provider_bpm = updates.get("provider_bpm", previous.provider_bpm)
        local_metadata_changed = (
            "analysis" in updates
            or "provider_key" in updates
            or "provider_camelot" in updates
            or "provider_bpm" in updates
        )
        if local_metadata_changed:
            display = metadata_display_fields(
                analysis,
                provider_key=provider_key,
                provider_camelot=provider_camelot,
                provider_bpm=provider_bpm,
            )
            key = display["key"]
            camelot = display["camelot"]
            bpm = display["bpm"]
            key_source = display["key_source"]
            bpm_source = display["bpm_source"]
        else:
            key = updates.get("key", previous.key)
            camelot = updates.get("camelot", previous.camelot)
            bpm = updates.get("bpm", previous.bpm)
            key_source = updates.get(
                "key_source",
                "local" if "key" in updates and key is not None else previous.key_source,
            )
            bpm_source = updates.get(
                "bpm_source",
                "local" if "bpm" in updates and bpm is not None else previous.bpm_source,
            )
            if "key" in updates and key is None:
                key_source = None
            if "camelot" in updates and camelot is None and "key" in updates:
                # Camelot is part of the same local key result, so an explicit
                # null key result clears its previous Camelot value as well.
                camelot = None
            if "bpm" in updates and bpm is None:
                bpm_source = None
        waveform_status = updates.get("waveform_status", previous.waveform_status)
        analysis_status = updates.get("analysis_status", previous.analysis_status)
        if "status" in updates:
            status = updates["status"]
        else:
            status = _overall_status(waveform_status, analysis_status)
        job.snapshot = PreviewMetadataSnapshot(
            track_id=previous.track_id,
            status=status,
            revision=previous.revision + 1,
            waveform=deepcopy(updates.get("waveform", previous.waveform)),
            key=key,
            camelot=camelot,
            bpm=bpm,
            error=updates.get("error", previous.error),
            waveform_status=waveform_status,
            analysis_status=analysis_status,
            analysis=analysis,
            analysis_error=updates.get("analysis_error", previous.analysis_error),
            key_source=key_source,
            bpm_source=bpm_source,
            provider_key=provider_key,
            provider_camelot=provider_camelot,
            provider_bpm=provider_bpm,
        )

    def retry_analysis(self, track_id: int) -> PreviewMetadataSnapshot | None:
        """Explicitly requeue a failed/deferred analysis for the saved source."""
        with self._lock:
            job = self._jobs.get(track_id)
            if job is None:
                return None
            if job.snapshot.analysis_status not in {"failed", "deferred"}:
                return self._clone_snapshot(job.snapshot)
            if job.task is not None and not job.task.done():
                return self._clone_snapshot(job.snapshot)
            if self.analysis_retry is None:
                raise RuntimeError("preview analysis retry is unavailable")
            if self._inflight_job_count_locked() >= _MAX_INFLIGHT_JOBS:
                raise PreviewJobQueueFullError(
                    "preview job capacity reached (one active source plus four waiting sources)"
                )
            loop = self._get_scheduling_loop()
            task = self._create_job_task(loop, job, retry=True)
            self._update_snapshot_locked(
                job,
                status="processing",
                analysis_status="queued",
                analysis_error=None,
                error=None,
            )
            job.completed_at_utc = None
            job.task = task
            return self._clone_snapshot(job.snapshot)

    async def close(self) -> None:
        """Cancel preview jobs and wait for their analyzer cleanup to finish."""
        current_loop = asyncio.get_running_loop()
        with self._lock:
            tasks = [
                job.task
                for job in (*self._jobs.values(), *self._retired_jobs)
                if job.task is not None and not job.task.done()
            ]
        same_loop = [task for task in tasks if task.get_loop() is current_loop]
        for task in tasks:
            task.cancel()
        if same_loop:
            await asyncio.gather(*same_loop, return_exceptions=True)

    def _prune_completed_jobs_locked(self) -> None:
        now = self._now_utc()
        self._retired_jobs = [
            job for job in self._retired_jobs
            if job.task is not None and not job.task.done()
        ]
        for track_id, job in list(self._jobs.items()):
            if job.task is None or not job.task.done():
                continue
            if job.completed_at_utc is None:
                job.completed_at_utc = now
            if now >= job.completed_at_utc + self._snapshot_ttl:
                del self._jobs[track_id]

        retained = sorted(
            (
                (job.completed_at_utc, track_id)
                for track_id, job in self._jobs.items()
                if job.task is not None and job.task.done()
            ),
            key=lambda item: item[0],
        )
        for _, track_id in retained[: max(0, len(retained) - self._max_retained_snapshots)]:
            del self._jobs[track_id]

    def _inflight_job_count_locked(self) -> int:
        return sum(
            1
            for job in (*self._jobs.values(), *self._retired_jobs)
            if job.task is not None and not job.task.done()
        )

    def _create_job_task(
        self,
        loop: asyncio.AbstractEventLoop,
        job: _PreviewJob,
        *,
        retry: bool = False,
    ) -> asyncio.Task[Any]:
        coroutine = self._run_job(job, retry=retry)
        try:
            return loop.create_task(coroutine)
        except Exception:
            coroutine.close()
            raise

    def _is_current_alias_locked(self, job: _PreviewJob) -> bool:
        if job.task is None or not job.task.done():
            return True
        if job.completed_at_utc is None:
            job.completed_at_utc = self._now_utc()
        return self._now_utc() < job.completed_at_utc + self._snapshot_ttl

    def _now_utc(self) -> datetime:
        current = self._clock()
        if (
            not isinstance(current, datetime)
            or current.tzinfo is None
            or current.utcoffset() is None
            or current.utcoffset().total_seconds() != 0
        ):
            raise ValueError("clock must return a timezone-aware UTC datetime")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _preview_identity(
        stream_url: str,
        duration: float | None,
        preview_profile: str,
        decoder_version: str | None,
        settings_identity: str | None,
    ) -> tuple[str, str, float | None, str | None, str | None]:
        source = _source_identity(stream_url)
        try:
            normalized_duration = float(duration) if duration is not None else None
        except (TypeError, ValueError, OverflowError):
            normalized_duration = None
        return source, preview_profile, normalized_duration, decoder_version, settings_identity

    def _shutdown(self) -> None:
        with self._lock:
            pending_tasks = [
                job.task
                for job in (*self._jobs.values(), *self._retired_jobs)
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
                for key in (
                    "waveform", "key", "camelot", "bpm",
                    "waveform_status", "analysis_status", "analysis", "analysis_error",
                    "key_source", "bpm_source",
                    "provider_key", "provider_camelot", "provider_bpm",
                )
                if key in result
            }
        return {
            key: getattr(result, key)
            for key in (
                "waveform", "key", "camelot", "bpm",
                "waveform_status", "analysis_status", "analysis", "analysis_error",
                "key_source", "bpm_source",
                "provider_key", "provider_camelot", "provider_bpm",
            )
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
            waveform_status=snapshot.waveform_status,
            analysis_status=snapshot.analysis_status,
            analysis=deepcopy(snapshot.analysis),
            analysis_error=snapshot.analysis_error,
            key_source=snapshot.key_source,
            bpm_source=snapshot.bpm_source,
            provider_key=snapshot.provider_key,
            provider_camelot=snapshot.provider_camelot,
            provider_bpm=snapshot.provider_bpm,
        )


def _waveform_is_usable(waveform: Any) -> bool:
    if not isinstance(waveform, dict):
        return False
    bands = waveform.get("bands")
    if bands is None:
        return bool(waveform)
    return isinstance(bands, dict) and all(
        isinstance(bands.get(name), list) and bool(bands[name])
        for name in ("low", "mid", "high")
    )


def _source_identity(stream_url: str) -> str:
    """Normalize the URL origin while preserving every query selector."""
    if not isinstance(stream_url, str):
        return repr(stream_url)
    try:
        parsed = urlsplit(stream_url)
    except ValueError:
        return stream_url
    if not parsed.scheme or not parsed.netloc:
        return stream_url

    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        parsed.query,
        "",
    ))


def _local_analysis_fields(analysis: Any) -> tuple[str | None, str | None, float | None]:
    if not isinstance(analysis, dict):
        return None, None, None
    key_data = analysis.get("key")
    rhythm_data = analysis.get("rhythm")
    key_data = key_data if isinstance(key_data, dict) else {}
    rhythm_data = rhythm_data if isinstance(rhythm_data, dict) else {}
    grid_data = rhythm_data.get("grid")
    grid_data = grid_data if isinstance(grid_data, dict) else {}
    key = key_data.get("key")
    camelot = key_data.get("camelot")
    bpm = grid_data.get("bpm")
    return key, camelot, bpm


def metadata_display_fields(
    analysis: Any,
    *,
    provider_key: str | None = None,
    provider_camelot: str | None = None,
    provider_bpm: float | None = None,
) -> dict[str, Any]:
    """Map analysis and provider metadata into additive legacy display fields."""
    local_key, local_camelot, local_bpm = _local_analysis_fields(analysis)
    return {
        "key": local_key if local_key is not None else provider_key,
        "camelot": local_camelot if local_camelot is not None else provider_camelot,
        "bpm": local_bpm if local_bpm is not None else provider_bpm,
        "key_source": (
            "local" if local_key is not None
            else "provider" if provider_key is not None
            else None
        ),
        "bpm_source": (
            "local" if local_bpm is not None
            else "provider" if provider_bpm is not None
            else None
        ),
    }


def _overall_status(waveform_status: str, analysis_status: str) -> PreviewStatus:
    if waveform_status == "failed":
        return "failed"
    if analysis_status in {"failed", "unknown", "deferred"}:
        return "partial" if waveform_status == "complete" else "failed"
    if waveform_status == "complete" and analysis_status == "complete":
        return "complete"
    if waveform_status == "queued" and analysis_status == "queued":
        return "queued"
    return "processing"
