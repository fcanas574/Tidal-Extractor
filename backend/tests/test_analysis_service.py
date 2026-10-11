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
    build_key_cache_key,
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
ZERO_SHA = "0" * 64


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
    def __init__(self, result=None, retry_result=None, progress=None):
        self.result = result or _result()
        self.retry_result = retry_result if retry_result is not None else self.result
        self.progress = progress
        self.calls = []
        self.retry_calls = []

    async def submit(self, job_id, wav_path, settings, *, on_progress=None):
        self.calls.append((job_id, Path(wav_path), settings))
        if self.progress is not None and on_progress is not None:
            callback_result = on_progress(self.progress)
            if hasattr(callback_result, "__await__"):
                await callback_result
        if callable(self.result):
            return self.result(job_id, settings)
        return self.result

    async def submit_retry(
        self, job_id, wav_path, settings, *, components, prior_result, on_progress=None
    ):
        self.retry_calls.append(
            (job_id, Path(wav_path), settings, frozenset(components), prior_result)
        )
        if callable(self.retry_result):
            return self.retry_result(job_id, settings)
        return self.retry_result


def _partial_result(settings=None, *, failed_component="rhythm"):
    result = _result(settings)
    if failed_component == "rhythm":
        failed_rhythm = replace(
            result.rhythm,
            bpm=None,
            beats=(),
            downbeats=(),
            grid=replace(
                result.rhythm.grid,
                bpm=None,
                period_seconds=None,
                origin_seconds=None,
                meter=None,
                first_downbeat_beat=None,
                status="failed",
                residual_p95_seconds=None,
                split_drift_seconds=None,
                reason="model unavailable",
            ),
            status="failed",
            reason="model unavailable",
        )
        return replace(result, rhythm=failed_rhythm)
    if failed_component == "key":
        return replace(
            result,
            key=replace(
                result.key,
                key=None,
                camelot=None,
                status="failed",
                candidates=(),
                agreement=None,
                reason="key analysis failed",
            ),
        )
    raise ValueError("failed_component must be key or rhythm")


def _unavailable_result(settings=None):
    result = _result(settings, model_sha256=ZERO_SHA)
    reason = "beat model unavailable"
    grid = replace(
        result.rhythm.grid,
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
    rhythm = replace(
        result.rhythm,
        bpm=None,
        beats=(),
        downbeats=(),
        grid=grid,
        status="unavailable",
        reason=reason,
    )
    return replace(result, rhythm=rhythm)


@pytest.mark.asyncio
async def test_service_publishes_rhythm_progress_as_partial_analysis(tmp_path):
    db = Database(":memory:")
    await db.init()
    settings = AnalysisSettings()
    worker = WorkerStub(progress={"rhythm": _result(settings).rhythm})
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    progress = []

    async def on_progress(snapshot):
        progress.append(snapshot)

    try:
        await service.analyze_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=settings,
            on_progress=on_progress,
        )

        assert len(progress) == 1
        assert progress[0]["analysis_status"] == "processing"
        assert progress[0]["analysis"]["rhythm"]["beats"] == [0.5, 1.0]
        assert progress[0]["analysis"]["key"] is None
    finally:
        await db.close()


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
async def test_current_pcm_cache_hit_works_without_preview_alias(tmp_path):
    db = Database(":memory:")
    await db.init()
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    settings = AnalysisSettings()
    engine_key = build_engine_key(settings, "decoder-v1", MODEL_SHA)
    cached = _result(fingerprint=PCM_SHA)
    await db.set_analysis_result(cached, engine_key)
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
async def test_unverified_model_result_caches_key_without_rhythm_data(tmp_path):
    db = Database(":memory:")
    await db.init()
    settings = AnalysisSettings()
    engine_key = build_engine_key(settings, "decoder-v1", MODEL_SHA)
    worker = WorkerStub(result=_result(settings, model_sha256=ZERO_SHA))
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
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
            settings=settings,
        )

        assert first.key.status == "reliable"
        assert first.model_sha256 == ZERO_SHA
        assert first.rhythm.status == "unavailable"
        assert first.rhythm.bpm is None
        assert first.rhythm.beats == ()
        assert first.rhythm.downbeats == ()
        assert first.rhythm.grid.status == "unavailable"
        assert first.rhythm.grid.bpm is None
        assert first.rhythm.grid.period_seconds is None
        assert first.rhythm.grid.origin_seconds is None
        assert first.rhythm.grid.meter is None
        assert first.rhythm.grid.first_downbeat_beat is None
        assert first.rhythm.grid.residual_p95_seconds is None
        assert first.rhythm.grid.split_drift_seconds is None
        assert await db.get_analysis_result(PCM_SHA, engine_key) is None
        key_cache_key = build_key_cache_key(settings, "decoder-v1")
        assert key_cache_key != engine_key
        cached = await db.get_analysis_result(PCM_SHA, key_cache_key)
        assert cached is not None
        assert cached == first
        assert cached.key == first.key
        assert cached.model_sha256 == ZERO_SHA
        assert cached.rhythm.status == "unavailable"
        assert cached.rhythm.bpm is None
        assert cached.rhythm.beats == ()
        assert cached.rhythm.downbeats == ()
        assert cached.rhythm.grid.status == "unavailable"
        assert cached.rhythm.grid.period_seconds is None

        second = await service.analyze_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=settings,
        )
        assert second == cached
        assert len(worker.calls) == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_explicit_retry_reuses_key_but_discards_unverified_rhythm(tmp_path):
    db = Database(":memory:")
    await db.init()
    settings = AnalysisSettings()
    model_available = False

    def resolve_model(_model_id):
        if not model_available:
            raise FileNotFoundError("beat model unavailable")
        return tmp_path / "final0.ckpt", MODEL_SHA

    worker = WorkerStub(
        result=_unavailable_result(settings),
        retry_result=_result(settings, model_sha256=ZERO_SHA),
    )
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=resolve_model,
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
            settings=settings,
        )
        assert first.key.status == "reliable"
        assert first.rhythm.status == "unavailable"

        model_available = True
        retried = await service.retry_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=settings,
        )

        assert worker.calls
        assert len(worker.calls) == 1
        assert len(worker.retry_calls) == 1
        _, _, _, components, prior_result = worker.retry_calls[0]
        assert components == frozenset({"rhythm"})
        assert prior_result.key == first.key
        assert prior_result.rhythm.status == "unavailable"
        assert prior_result.rhythm.beats == ()
        assert retried.key == first.key
        assert retried.model_sha256 == ZERO_SHA
        assert retried.rhythm.status == "unavailable"
        assert retried.rhythm.bpm is None
        assert retried.rhythm.beats == ()
        assert retried.rhythm.downbeats == ()
        assert retried.rhythm.grid.status == "unavailable"
        assert retried.rhythm.grid.bpm is None
        assert retried.rhythm.grid.period_seconds is None
        assert retried.rhythm.grid.origin_seconds is None
        assert retried.rhythm.grid.meter is None
        assert retried.rhythm.grid.first_downbeat_beat is None
        assert retried.rhythm.grid.residual_p95_seconds is None
        assert retried.rhythm.grid.split_drift_seconds is None
        engine_key = build_engine_key(settings, "decoder-v1", MODEL_SHA)
        key_cache_key = build_key_cache_key(settings, "decoder-v1")
        assert await db.get_analysis_result(PCM_SHA, engine_key) is None
        assert await db.get_analysis_result(PCM_SHA, key_cache_key) == retried
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_explicit_retry_reruns_failed_component_and_preserves_cached_success(tmp_path):
    db = Database(":memory:")
    await db.init()
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    settings = AnalysisSettings()
    engine_key = build_engine_key(settings, "decoder-v1", MODEL_SHA)
    partial = _partial_result(settings, failed_component="rhythm")
    recomputed = replace(
        _result(settings),
        key=replace(
            _result(settings).key,
            key="D minor",
            camelot="7A",
        ),
    )
    await db.set_analysis_result(partial, engine_key)
    worker = WorkerStub(retry_result=recomputed)
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
        clock=lambda: now,
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    try:
        result = await service.retry_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=settings,
        )

        assert worker.calls == []
        assert len(worker.retry_calls) == 1
        _, submitted_path, submitted_settings, components, prior_result = worker.retry_calls[0]
        assert submitted_path == wav_path
        assert submitted_settings == settings
        assert components == frozenset({"rhythm"})
        assert prior_result == partial
        assert result.key == partial.key
        assert result.rhythm == recomputed.rhythm
        assert await db.get_analysis_result(PCM_SHA, engine_key) == result
        assert await db.get_preview_analysis_alias(
            track_id=42,
            profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            engine_key=engine_key,
            now_utc=now,
        ) == PCM_SHA
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_explicit_retry_runs_both_components_without_matching_cached_pcm(tmp_path):
    db = Database(":memory:")
    await db.init()
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    settings = AnalysisSettings()
    engine_key = build_engine_key(settings, "decoder-v1", MODEL_SHA)
    other_fingerprint = "c" * 64
    await db.set_analysis_result(_result(settings, fingerprint=other_fingerprint), engine_key)
    await db.set_preview_analysis_alias(
        track_id=42,
        profile="high_lossless",
        duration_seconds=12.5,
        decoder_version="decoder-v1",
        engine_key=engine_key,
        fingerprint=other_fingerprint,
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
        result = await service.retry_preview(
            track_id=42,
            wav_path=wav_path,
            pcm_sha256=PCM_SHA,
            preview_profile="high_lossless",
            duration_seconds=12.5,
            decoder_version="decoder-v1",
            settings=settings,
        )

        assert len(worker.retry_calls) == 1
        _, _, _, components, prior_result = worker.retry_calls[0]
        assert components == frozenset({"key", "rhythm"})
        assert prior_result is None
        assert result.audio_fingerprint == PCM_SHA
        assert await db.get_analysis_result(PCM_SHA, engine_key) == result
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_explicit_retry_returns_full_success_cache_without_worker_work(tmp_path):
    db = Database(":memory:")
    await db.init()
    settings = AnalysisSettings()
    engine_key = build_engine_key(settings, "decoder-v1", MODEL_SHA)
    cached = _result(settings)
    await db.set_analysis_result(cached, engine_key)
    worker = WorkerStub()
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
    )
    wav_path = tmp_path / "preview.wav"
    wav_path.write_bytes(b"decoded audio")
    try:
        result = await service.retry_preview(
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
        assert worker.retry_calls == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_ordinary_analysis_cache_lookup_does_not_retry_partial_result(tmp_path):
    db = Database(":memory:")
    await db.init()
    settings = AnalysisSettings()
    engine_key = build_engine_key(settings, "decoder-v1", MODEL_SHA)
    partial = _partial_result(settings, failed_component="key")
    await db.set_analysis_result(partial, engine_key)
    worker = WorkerStub()
    service = AnalysisService(
        db,
        worker=worker,
        model_identity_resolver=lambda _model_id: (tmp_path / "final0.ckpt", MODEL_SHA),
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

        assert result == partial
        assert worker.calls == []
        assert worker.retry_calls == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_live_preview_alias_with_different_pcm_does_not_return_other_audio(tmp_path):
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
        assert result.audio_fingerprint == PCM_SHA
        assert result != cached
        assert len(worker.calls) == 1
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
