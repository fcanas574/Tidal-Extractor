from datetime import datetime, timedelta, timezone

import pytest

from backend.analysis.types import (
    GridResult,
    HybridAnalysisResult,
    KeyCandidate,
    KeyResult,
    RhythmResult,
)
from backend.models import Database


def _result(fingerprint="a" * 64):
    grid = GridResult(
        bpm=120.0,
        period_seconds=0.5,
        origin_seconds=0.0,
        meter="4/4",
        first_downbeat_beat=0,
        status="reliable",
        residual_p95_seconds=0.01,
        split_drift_seconds=0.01,
        reason=None,
    )
    return HybridAnalysisResult(
        schema_version=1,
        audio_fingerprint=fingerprint,
        decoder_version="decoder-v1",
        duration_seconds=2.0,
        model_id="final0",
        model_sha256="b" * 64,
        key_profile_id="temperley-2002-figure1-v1",
        settings_sha256="c" * 64,
        key=KeyResult(
            key="C major",
            camelot="8B",
            status="reliable",
            candidates=(KeyCandidate(tonic_pc=0, mode="major", score=0.9),),
            agreement=1.0,
            reason=None,
        ),
        rhythm=RhythmResult(
            bpm=120.0,
            beats=(0.5, 1.0),
            downbeats=(0.5,),
            grid=grid,
            status="reliable",
            reason=None,
        ),
    )


@pytest.mark.asyncio
async def test_analysis_result_round_trips_by_fingerprint_and_engine_key():
    db = Database(":memory:")
    await db.init()
    try:
        result = _result()
        engine_key = "d" * 64

        assert await db.get_analysis_result(result.audio_fingerprint, engine_key) is None
        await db.set_analysis_result(result, engine_key)
        loaded = await db.get_analysis_result(result.audio_fingerprint, engine_key)

        assert loaded == result
        assert await db.get_analysis_result(result.audio_fingerprint, "e" * 64) is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_alias_expires_and_engine_identity_invalidates():
    db = Database(":memory:")
    await db.init()
    try:
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        expires_at = now + timedelta(hours=24)
        identity = {
            "track_id": 42,
            "profile": "high_lossless",
            "duration_seconds": 183.25,
            "decoder_version": "decoder-v1",
            "engine_key": "d" * 64,
        }
        await db.set_preview_analysis_alias(
            **identity,
            fingerprint="a" * 64,
            expires_at_utc=expires_at,
        )

        assert (
            await db.get_preview_analysis_alias(
                **identity, now_utc=now + timedelta(seconds=1)
            )
            == "a" * 64
        )
        assert (
            await db.get_preview_analysis_alias(
                **identity, now_utc=expires_at
            )
            is None
        )
        assert (
            await db.get_preview_analysis_alias(
                **{**identity, "engine_key": "e" * 64},
                now_utc=now + timedelta(seconds=1),
            )
            is None
        )
    finally:
        await db.close()
