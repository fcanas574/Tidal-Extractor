"""Cache-backed orchestration for preview audio analysis."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Callable

from backend.analysis.types import AnalysisSettings, HybridAnalysisResult, serialize_result
from backend.analysis.worker import AnalysisWorker


ENGINE_VERSION = "preview-hybrid-v1"
PREVIEW_ALIAS_TTL = timedelta(hours=24)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ZERO_SHA256 = "0" * 64


def _normalize_sha256(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a 64-character SHA-256 hex digest")
    return value.lower()


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def build_engine_key(
    settings: AnalysisSettings,
    decoder_version: str,
    model_sha256: str,
    *,
    engine_version: str = ENGINE_VERSION,
) -> str:
    """Hash every result-affecting engine, decoder, model and settings identity."""
    if not isinstance(settings, AnalysisSettings):
        raise TypeError("settings must be AnalysisSettings")
    if not isinstance(engine_version, str) or not engine_version:
        raise ValueError("engine_version must be a non-empty string")
    if not isinstance(decoder_version, str) or not decoder_version:
        raise ValueError("decoder_version must be a non-empty string")
    digest = _normalize_sha256(model_sha256, "model_sha256")
    payload = {
        "engine_version": engine_version,
        "schema_version": settings.schema_version,
        "decoder_version": decoder_version,
        "model_id": settings.model_id,
        "model_sha256": digest,
        "key_profile_id": settings.key_profile_id,
        "settings_sha256": settings.sha256,
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _verified_model_identity(model_id: str) -> tuple[Path, str]:
    """Resolve Task 4's verified local file without loading inference packages.

    The public ``get_model_path`` also validates installed runtime packages and
    therefore imports Beat This!/PyTorch. This lightweight check reuses Task 4's
    manifest/archive/file digest verifier in the parent; actual model loading and
    the full runtime check stay in the spawned child through Task 3.
    """
    from scripts.setup_analysis_model import _sha256_file, _verified_local_model

    path = _verified_local_model(model_id)
    digest = _normalize_sha256(_sha256_file(path), "model_sha256")
    return Path(path), digest


class AnalysisService:
    """Resolve preview cache identities and submit only actual cache misses."""

    def __init__(
        self,
        db,
        *,
        worker: AnalysisWorker | None = None,
        model_identity_resolver: Callable[[str], tuple[Path, str]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.worker = worker or AnalysisWorker()
        self._model_identity_resolver = model_identity_resolver or _verified_model_identity
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now_utc(self) -> datetime:
        current = self._clock()
        if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware UTC datetime")
        if current.utcoffset().total_seconds() != 0:
            raise ValueError("clock must return a timezone-aware UTC datetime")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _validate_request(
        track_id: int,
        pcm_sha256: str,
        preview_profile: str,
        duration_seconds: float,
        decoder_version: str,
        settings: AnalysisSettings,
    ) -> tuple[str, float]:
        if isinstance(track_id, bool) or not isinstance(track_id, int) or track_id <= 0:
            raise ValueError("track_id must be a positive integer")
        fingerprint = _normalize_sha256(pcm_sha256, "pcm_sha256")
        if not isinstance(preview_profile, str) or not preview_profile:
            raise ValueError("preview_profile must be a non-empty string")
        if not isinstance(decoder_version, str) or not decoder_version:
            raise ValueError("decoder_version must be a non-empty string")
        if not isinstance(settings, AnalysisSettings):
            raise TypeError("settings must be AnalysisSettings")
        if not isinstance(settings.model_id, str) or not settings.model_id:
            raise ValueError("settings.model_id must be a non-empty string")
        if not isinstance(settings.key_profile_id, str) or not settings.key_profile_id:
            raise ValueError("settings.key_profile_id must be a non-empty string")
        for name in (
            "key_sample_rate",
            "key_hop_length",
            "tempo_minimum_beats",
            "downbeat_minimum_events",
            "schema_version",
        ):
            value = getattr(settings, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"settings.{name} must be a positive integer")
        for name in (
            "tempo_minimum_coverage",
            "downbeat_phase_agreement",
        ):
            value = getattr(settings, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"settings.{name} must be finite and between 0 and 1")
        for name in (
            "grid_p95_tolerance_seconds",
            "grid_split_drift_tolerance_seconds",
            "downbeat_tolerance_seconds",
        ):
            value = getattr(settings, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"settings.{name} must be finite and non-negative")
        try:
            if isinstance(duration_seconds, bool):
                raise ValueError
            duration = float(duration_seconds)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("duration_seconds must be finite and positive") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("duration_seconds must be finite and positive")
        # Accessing the canonical settings digest rejects non-JSON values early.
        _ = settings.sha256
        return fingerprint, duration

    @staticmethod
    def _result_matches(
        result: HybridAnalysisResult,
        *,
        fingerprint: str,
        decoder_version: str,
        duration_seconds: float,
        settings: AnalysisSettings,
        model_sha256: str,
    ) -> bool:
        return (
            result.audio_fingerprint.lower() == fingerprint
            and result.schema_version == settings.schema_version
            and result.decoder_version == decoder_version
            and result.duration_seconds == duration_seconds
            and result.model_id == settings.model_id
            and result.model_sha256.lower() == model_sha256
            and result.key_profile_id == settings.key_profile_id
            and result.settings_sha256 == settings.sha256
        )

    async def _resolve_model_identity(self, model_id: str) -> tuple[Path, str] | None:
        try:
            path, model_sha256 = await asyncio.to_thread(
                self._model_identity_resolver, model_id
            )
            digest = _normalize_sha256(model_sha256, "model_sha256")
            return Path(path), digest
        except (FileNotFoundError, OSError, RuntimeError, ValueError):
            # A missing or invalid optional model disables result/alias caching.
            # The key component still runs in the child and rhythm reports its
            # own verified-model error without provisioning anything implicitly.
            return None

    def _worker_job_id(
        self,
        *,
        fingerprint: str,
        preview_profile: str,
        duration_seconds: float,
        decoder_version: str,
        engine_key: str | None,
        settings: AnalysisSettings,
    ) -> str:
        identity = {
            "audio_fingerprint": fingerprint,
            "preview_profile": preview_profile,
            "duration_seconds": duration_seconds,
            "decoder_version": decoder_version,
            "engine_key": engine_key or "unverified-model",
            "settings_sha256": settings.sha256,
        }
        return hashlib.sha256(_canonical_json(identity)).hexdigest()

    async def _write_preview_alias(
        self,
        *,
        track_id: int,
        preview_profile: str,
        duration_seconds: float,
        decoder_version: str,
        engine_key: str,
        fingerprint: str,
    ) -> None:
        # This UTC instant is the caller-owned write time passed to persistence;
        # expiry is exactly 24 hours after it, with no rounding or extension.
        written_at = self._now_utc()
        await self.db.set_preview_analysis_alias(
            track_id=track_id,
            profile=preview_profile,
            duration_seconds=duration_seconds,
            decoder_version=decoder_version,
            engine_key=engine_key,
            fingerprint=fingerprint,
            expires_at_utc=written_at + PREVIEW_ALIAS_TTL,
        )

    async def analyze_preview(
        self,
        track_id: int,
        wav_path: Path,
        pcm_sha256: str,
        preview_profile: str,
        duration_seconds: float,
        decoder_version: str,
        settings: AnalysisSettings,
    ) -> HybridAnalysisResult:
        """Return a cached result or enqueue a single hybrid analysis job."""
        fingerprint, duration = self._validate_request(
            track_id,
            pcm_sha256,
            preview_profile,
            duration_seconds,
            decoder_version,
            settings,
        )
        model_identity = await self._resolve_model_identity(settings.model_id)
        model_path = model_identity[0] if model_identity is not None else None
        model_sha256 = model_identity[1] if model_identity is not None else None
        engine_key = (
            build_engine_key(settings, decoder_version, model_sha256)
            if model_sha256 is not None
            else None
        )

        if engine_key is not None:
            alias_fingerprint = await self.db.get_preview_analysis_alias(
                track_id=track_id,
                profile=preview_profile,
                duration_seconds=duration,
                decoder_version=decoder_version,
                engine_key=engine_key,
                now_utc=self._now_utc(),
            )
            if alias_fingerprint == fingerprint:
                alias_result = await self.db.get_analysis_result(alias_fingerprint, engine_key)
                if alias_result is not None and self._result_matches(
                    alias_result,
                    fingerprint=alias_fingerprint,
                    decoder_version=decoder_version,
                    duration_seconds=duration,
                    settings=settings,
                    model_sha256=model_sha256,
                ):
                    return alias_result

            cached_result = await self.db.get_analysis_result(fingerprint, engine_key)
            if cached_result is not None and self._result_matches(
                cached_result,
                fingerprint=fingerprint,
                decoder_version=decoder_version,
                duration_seconds=duration,
                settings=settings,
                model_sha256=model_sha256,
            ):
                await self._write_preview_alias(
                    track_id=track_id,
                    preview_profile=preview_profile,
                    duration_seconds=duration,
                    decoder_version=decoder_version,
                    engine_key=engine_key,
                    fingerprint=fingerprint,
                )
                return cached_result

        job_id = self._worker_job_id(
            fingerprint=fingerprint,
            preview_profile=preview_profile,
            duration_seconds=duration,
            decoder_version=decoder_version,
            engine_key=engine_key,
            settings=settings,
        )
        raw_result = await self.worker.submit(job_id, Path(wav_path), settings)
        if not isinstance(raw_result, HybridAnalysisResult):
            raise TypeError("analysis worker must return HybridAnalysisResult")

        worker_model_sha = _normalize_sha256(raw_result.model_sha256, "model_sha256")
        result = replace(
            raw_result,
            schema_version=settings.schema_version,
            audio_fingerprint=fingerprint,
            decoder_version=decoder_version,
            duration_seconds=duration,
            model_id=settings.model_id,
            model_sha256=worker_model_sha,
            key_profile_id=settings.key_profile_id,
            settings_sha256=settings.sha256,
        )
        # Validate caller identity and event times before storing or returning a
        # result that claims to correspond to this decoded preview.
        serialize_result(result)

        if (
            engine_key is not None
            and model_path is not None
            and model_sha256 is not None
            and worker_model_sha == model_sha256
        ):
            await self.db.set_analysis_result(result, engine_key)
            await self._write_preview_alias(
                track_id=track_id,
                preview_profile=preview_profile,
                duration_seconds=duration,
                decoder_version=decoder_version,
                engine_key=engine_key,
                fingerprint=fingerprint,
            )
        return result
