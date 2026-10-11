from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from backend.analysis.service import (
    ENGINE_VERSION,
    AnalysisService,
    build_engine_key,
)
from backend.analysis.types import (
    AnalysisSettings,
    GridResult,
    HybridAnalysisResult,
    KeyCandidate,
    KeyResult,
    RhythmResult,
)
from backend.models import Database


MODEL_SHA = "b" * 64
PCM_SHA = "a" * 64


def _result(settings=None, fingerprint=PCM_SHA, model_sha256=MODEL_SHA):
    settings = settings or AnalysisSettings()
    return HybridAnalysisResult(
        schema_version=settings.schema_version,
        audio_fingerprint=fingerprint,
        decoder_version="decoder-v1",
        duration_seconds=12.5,
        model_id=settings.model_id,
        model_sha256=model_sha256,
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
            bpm=120.0,
            beats=(0.5, 1.0),
            downbeats=(0.5,),
            grid=GridResult(
                bpm=120.0,
                period_seconds=0.5,
                origin_seconds=0.0,
                meter="4/4",
                first_downbeat_beat=0,
                status="reliable",
                residual_p95_seconds=0.01,
                split_drift_seconds=0.01,
                reason=None,
            ),
            status="reliable",
            reason=None,
        ),
    )


class WorkerStub:
    def __init__(self, result=None):
        self.result = result or _result()
        self.calls = []

    async def submit(self, job_id, wav_path, settings):
        self.calls.append((job_id, Path(wav_path), settings))
        if callable(self.result):
            return self.result(job_id, settings)
        return self.result


@pytest.mark.asyncio
async def test_analysis_cache_hit_skips_worker(tmp_path):
    db = Database(":memory:")
    await db.init()
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    worker = WorkerStub()
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
        clock=lambda: now,
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    try:
        first = await service.analyze_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=AnalysisSettings(),
        )
        second = await service.analyze_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=AnalysisSettings(),
        )
        assert first == second
        assert len(worker.calls) == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_live_preview_alias_returns_cached_result_without_worker(tmp_path):
    db = Database(":memory:")
    await db.init()
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    settings = AnalysisSettings()
    engine_key = build_engine_key(settings, "decoder-v1", MODEL_SHA)
    aliased_fingerprint = "c" * 64
    cached = _result(fingerprint=aliased_fingerprint)
    await db.set_analysis_result(cached, engine_key)
    await db.set_preview_analysis_alias(
        track_id=42,
        profile="high_lossless",
        duration_seconds=12.5,
        decoder_version="decoder-v1",
        engine_key=engine_key,
        fingerprint=aliased_fingerprint,
        expires_at_utc=now + timedelta(hours=24),
    )
    worker = WorkerStub()
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
        clock=lambda: now,
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    try:
        result = await service.analyze_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=settings,
        )
        assert result == cached
        assert worker.calls == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_alias_is_live_until_exactly_24_hours_after_utc_write(tmp_path):
    db = Database(":memory:")
    await db.init()
    written_at = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    worker = WorkerStub()
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
        clock=lambda: written_at,
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    identity = {
        "track_id": 42,
        "profile": "high_lossless",
        "duration_seconds": 12.5,
        "decoder_version": "decoder-v1",
        "engine_key": build_engine_key(AnalysisSettings(), "decoder-v1", MODEL_SHA),
    }
    try:
        await service.analyze_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=AnalysisSettings(),
        )
        assert await db.get_preview_analysis_alias(
            **identity,
            now_utc=written_at + timedelta(hours=24) - timedelta(microseconds=1),
        ) == PCM_SHA
        assert await db.get_preview_analysis_alias(
            **identity,
            now_utc=written_at + timedelta(hours=24),
        ) is None
    finally:
        await db.close()


def test_engine_key_hashes_each_result_affecting_identity():
    settings = AnalysisSettings()
    baseline = build_engine_key(settings, "decoder-v1", MODEL_SHA)
    expected_payload = {
        "engine_version": ENGINE_VERSION,
        "schema_version": 1,
        "decoder_version": "decoder-v1",
        "model_id": "final0",
        "model_sha256": MODEL_SHA,
        "key_profile_id": "temperley-2002-figure1-v1",
        "settings_sha256": settings.sha256,
    }
    expected = hashlib.sha256(
        json.dumps(expected_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    assert baseline == expected
    assert build_engine_key(settings, "decoder-v2", MODEL_SHA) != baseline
    assert build_engine_key(settings, "decoder-v1", "c" * 64) != baseline
    assert build_engine_key(replace(settings, model_id="other-model"), "decoder-v1", MODEL_SHA) != baseline
    assert build_engine_key(replace(settings, key_profile_id="other-profile"), "decoder-v1", MODEL_SHA) != baseline
    assert build_engine_key(replace(settings, schema_version=2), "decoder-v1", MODEL_SHA) != baseline
    assert build_engine_key(replace(settings, tempo_minimum_beats=33), "decoder-v1", MODEL_SHA) != baseline
    assert build_engine_key(settings, "decoder-v1", MODEL_SHA, engine_version="preview-hybrid-v2") != baseline


@pytest.mark.asyncio
async def test_decoder_identity_change_does_not_hit_old_alias_or_result(tmp_path):
    db = Database(":memory:")
    await db.init()
    worker = WorkerStub()
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
        clock=lambda: now,
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    try:
        for decoder_version in ("decoder-v1", "decoder-v2"):
            await service.analyze_preview(
                track_id=42,
                wav_path=wav_path,
                pcm_sha256=PCM_SHA,
                preview_profile="high_lossless",
                duration_seconds=12.5,
                decoder_version=decoder_version,
                settings=AnalysisSettings(),
            )
        assert len(worker.calls) == 2
        assert worker.calls[0][0] != worker.calls[1][0]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_model_and_settings_identity_changes_miss_old_alias_and_result(tmp_path):
    db = Database(":memory:")
    await db.init()
    model_sha = [MODEL_SHA]
    worker = WorkerStub(result=lambda _job_id, settings: _result(settings, model_sha256=model_sha[0]))
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", model_sha[0]),
        clock=lambda: datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    calls = (
        ("decoder-v1", AnalysisSettings()),
        ("decoder-v1", replace(AnalysisSettings(), schema_version=2)),
        ("decoder-v1", replace(AnalysisSettings(), key_profile_id="other-profile")),
        ("decoder-v1", replace(AnalysisSettings(), tempo_minimum_beats=33)),
        ("decoder-v1", replace(AnalysisSettings(), model_id="other-model")),
    )
    try:
        for decoder_version, settings in calls:
            await service.analyze_preview(
                track_id=42,
                wav_path=wav_path,
                pcm_sha256=PCM_SHA,
                preview_profile="high_lossless",
                duration_seconds=12.5,
                decoder_version=decoder_version,
                settings=settings,
            )
        model_sha[0] = "c" * 64
        await service.analyze_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=AnalysisSettings(),
        )
        assert len(worker.calls) == 6
        assert len({call[0] for call in worker.calls}) == 6
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_invalid_pcm_identity_is_not_cached_or_aliased(tmp_path):
    db = Database(":memory:")
    await db.init()
    worker = WorkerStub()
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    try:
        with pytest.raises(ValueError):
            await service.analyze_preview(
                track_id=42,
                wav_path=wav_path,
                pcm_sha256="not-a-pcm-digest",
                preview_profile="high_lossless",
                duration_seconds=12.5,
                decoder_version="decoder-v1",
                settings=AnalysisSettings(),
            )
        assert worker.calls == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_invalid_settings_are_rejected_before_worker_or_alias_write(tmp_path):
    db = Database(":memory:")
    await db.init()
    worker = WorkerStub()
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    try:
        with pytest.raises(ValueError):
            await service.analyze_preview(
                track_id=42,
                wav_path=wav_path,
                pcm_sha256=PCM_SHA,
                preview_profile="high_lossless",
                duration_seconds=12.5,
                decoder_version="decoder-v1",
                settings=replace(AnalysisSettings(), key_profile_id=""),
            )
        assert worker.calls == []
    finally:
        await db.close()
