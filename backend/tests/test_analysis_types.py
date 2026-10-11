import hashlib
import json
from dataclasses import replace

import pytest

from backend.analysis.types import (
    AnalysisSettings,
    GridResult,
    HybridAnalysisResult,
    KeyCandidate,
    KeyResult,
    RhythmResult,
    camelot_for_key,
    deserialize_result,
    serialize_result,
)
from backend.analysis.rhythm_engine import fit_steady_grid


def _result(*, key_bpm=120.0, beats=(0.5, 1.0), downbeats=(0.5,)):
    grid = GridResult(
        bpm=key_bpm,
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
        audio_fingerprint="a" * 64,
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
            bpm=key_bpm,
            beats=beats,
            downbeats=downbeats,
            grid=grid,
            status="reliable",
            reason=None,
        ),
    )


def test_analysis_settings_use_canonical_json_identity():
    settings = AnalysisSettings()
    expected = (
        b'{"downbeat_minimum_events":8,"downbeat_phase_agreement":0.9,'
        b'"downbeat_tolerance_seconds":0.05,"grid_p95_tolerance_seconds":0.035,'
        b'"grid_split_drift_tolerance_seconds":0.04,"key_hop_length":512,'
        b'"key_profile_id":"temperley-2002-figure1-v1","key_sample_rate":22050,'
        b'"model_id":"final0","schema_version":1,"tempo_minimum_beats":32,'
        b'"tempo_minimum_coverage":0.5}'
    )

    assert settings.canonical_json_bytes == expected
    assert settings.sha256 == hashlib.sha256(expected).hexdigest()
    assert replace(settings, key_hop_length=513).sha256 != settings.sha256


def test_camelot_contract_accepts_all_24_pairs():
    expected_by_key = {
        (0, "major"): "8B",
        (1, "major"): "3B",
        (2, "major"): "10B",
        (3, "major"): "5B",
        (4, "major"): "12B",
        (5, "major"): "7B",
        (6, "major"): "2B",
        (7, "major"): "9B",
        (8, "major"): "4B",
        (9, "major"): "11B",
        (10, "major"): "6B",
        (11, "major"): "1B",
        (0, "minor"): "5A",
        (1, "minor"): "12A",
        (2, "minor"): "7A",
        (3, "minor"): "2A",
        (4, "minor"): "9A",
        (5, "minor"): "4A",
        (6, "minor"): "11A",
        (7, "minor"): "6A",
        (8, "minor"): "1A",
        (9, "minor"): "8A",
        (10, "minor"): "3A",
        (11, "minor"): "10A",
    }
    map_for_all_24_keys = {
        (tonic_pc, mode): camelot_for_key(tonic_pc, mode)
        for tonic_pc in range(12)
        for mode in ("major", "minor")
    }

    assert map_for_all_24_keys == expected_by_key
    assert set(map_for_all_24_keys.values()) == {
        f"{number}{mode}" for number in range(1, 13) for mode in "AB"
    }


def test_serialization_rejects_nonfinite_and_out_of_duration_times():
    with pytest.raises(ValueError):
        serialize_result(_result(key_bpm=float("nan")))

    with pytest.raises(ValueError):
        serialize_result(_result(beats=(0.5, 2.01)))


def test_serialization_preserves_typed_result_as_json_data():
    result = _result()

    serialized = serialize_result(result)

    assert serialized["audio_fingerprint"] == "a" * 64
    assert serialized["key"]["candidates"][0] == {
        "tonic_pc": 0,
        "mode": "major",
        "score": 0.9,
    }
    assert serialized["rhythm"]["beats"] == [0.5, 1.0]
    json.dumps(serialized, allow_nan=False)


def test_serialization_preserves_tempo_ambiguity_diagnostic():
    beat_times = tuple(0.13 + index for index in range(40))
    downbeat_times = tuple(beat_times[index] for index in range(0, 40, 4))
    rhythm = fit_steady_grid(beat_times, downbeat_times, 40.2)
    result = replace(_result(), duration_seconds=40.2, rhythm=rhythm)

    serialized = serialize_result(result)
    restored = deserialize_result(serialized)

    assert serialized["rhythm"]["status"] == "needs_review"
    assert serialized["rhythm"]["bpm"] == rhythm.bpm
    assert serialized["rhythm"]["reason"] == rhythm.reason
    assert serialized["rhythm"]["grid"]["status"] == "needs_review"
    assert serialized["rhythm"]["grid"]["bpm"] is None
    assert serialized["rhythm"]["grid"]["reason"] == rhythm.grid.reason
    assert restored.rhythm == rhythm
