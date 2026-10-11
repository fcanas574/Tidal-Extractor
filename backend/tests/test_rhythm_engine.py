import hashlib
import math

from backend.analysis.types import AnalysisSettings
from backend.analysis import rhythm_engine
from backend.analysis.rhythm_engine import estimate_rhythm, fit_steady_grid


def _beats(bpm: float, count: int, origin: float = 0.0) -> tuple[float, ...]:
    period = 60.0 / bpm
    return tuple(origin + index * period for index in range(count))


def _downbeats(beat_times: tuple[float, ...], indices: tuple[int, ...]) -> tuple[float, ...]:
    return tuple(beat_times[index] for index in indices)


def test_grid_fit_preserves_fractional_bpm_and_origin():
    bpm = 128.24
    origin = 0.137
    beat_times = _beats(bpm, 64, origin)
    downbeat_times = _downbeats(beat_times, tuple(range(3, 64, 4)))

    result = fit_steady_grid(beat_times, downbeat_times, 30.0)

    assert result.grid.status == "reliable"
    assert result.grid.bpm is not None
    assert abs(result.grid.bpm - bpm) < 1e-3
    assert result.grid.origin_seconds is not None
    assert abs(result.grid.origin_seconds - origin) < 0.005
    assert result.grid.first_downbeat_beat == 3


def test_missing_beats_keep_integer_beat_numbers():
    source_indices = tuple(index for index in range(64) if index not in {12, 29})
    beat_times = tuple(0.08 + index * 0.5 for index in source_indices)
    downbeat_times = tuple(0.08 + index * 0.5 for index in range(2, 64, 4))

    result = fit_steady_grid(beat_times, downbeat_times, 32.0)

    assert result.grid.status == "reliable"
    assert result.grid.bpm is not None
    assert abs(result.grid.bpm - 120.0) < 1e-3
    assert result.grid.first_downbeat_beat == 2
    assert result.grid.period_seconds == 0.5


def test_drift_over_threshold_withholds_grid_and_keeps_raw_events():
    origin = 0.1
    beat_times = tuple(
        origin + index * 0.5 + (0.12 if index >= 32 else 0.0)
        for index in range(64)
    )

    result = fit_steady_grid(beat_times, (), 32.0)

    assert result.grid.status == "needs_review"
    assert result.grid.bpm is None
    assert result.grid.residual_p95_seconds is not None
    assert result.grid.split_drift_seconds is not None
    assert result.grid.split_drift_seconds > 0.040
    assert result.status == "needs_review"
    assert result.beats == beat_times


def test_bar_phase_requires_eight_consistent_downbeats():
    beat_times = _beats(120.0, 64, 0.08)
    seven_downbeats = _downbeats(beat_times, (2, 6, 10, 14, 18, 22, 26))
    eight_downbeats = _downbeats(beat_times, (2, 6, 10, 14, 18, 22, 26, 30))

    seven = fit_steady_grid(beat_times, seven_downbeats, 32.0)
    eight = fit_steady_grid(beat_times, eight_downbeats, 32.0)

    assert seven.grid.status == "reliable"
    assert seven.grid.meter is None
    assert seven.grid.first_downbeat_beat is None
    assert eight.grid.status == "reliable"
    assert eight.grid.meter == "4/4"
    assert eight.grid.first_downbeat_beat == 2


def test_short_or_empty_sequence_has_no_grid():
    short_beats = _beats(120.0, 24, 0.05)

    short = fit_steady_grid(short_beats, (), 40.0)
    empty = fit_steady_grid((), (), 40.0)

    assert short.grid.status == "needs_review"
    assert short.grid.bpm is None
    assert short.grid.period_seconds is None
    assert empty.grid.status == "needs_review"
    assert empty.grid.bpm is None
    assert empty.grid.period_seconds is None


def test_malformed_and_out_of_duration_events_are_ignored():
    valid = _beats(120.0, 64, 0.05)
    duration = 32.0
    raw_beats = (
        *valid[:10],
        math.nan,
        -0.01,
        valid[9],
        valid[9] - 0.2,
        duration + 1.0,
        *valid[10:],
    )
    raw_downbeats = (valid[0], math.inf, valid[0], duration + 1.0, *valid[4::4])

    result = fit_steady_grid(raw_beats, raw_downbeats, duration)

    assert result.beats == valid
    assert result.downbeats == (valid[0], *valid[4::4])
    assert result.grid.status == "reliable"


def test_conflicting_downbeat_phase_is_not_accepted():
    beat_times = _beats(120.0, 64, 0.08)
    downbeat_times = _downbeats(beat_times, (0, 4, 8, 12, 16, 20, 24, 28, 35))

    result = fit_steady_grid(beat_times, downbeat_times, 32.0)

    assert result.grid.status == "reliable"
    assert result.grid.meter is None
    assert result.grid.first_downbeat_beat is None


def test_half_double_tempo_ambiguity_keeps_observed_period():
    beat_times = _beats(60.0, 40, 0.13)
    downbeat_times = _downbeats(beat_times, tuple(range(0, 40, 4)))

    result = fit_steady_grid(beat_times, downbeat_times, 40.2)

    assert result.grid.status == "reliable"
    assert result.grid.bpm is not None
    assert abs(result.grid.bpm - 60.0) < 1e-3
    assert result.grid.period_seconds == 1.0


def test_irregular_false_positive_sequence_withholds_grid():
    beat_times = tuple(
        0.1 + index * 0.5 + 0.09 * math.sin(index * 1.7)
        for index in range(64)
    )

    result = fit_steady_grid(beat_times, (), 32.0)

    assert result.grid.status == "needs_review"
    assert result.grid.bpm is None
    assert result.grid.residual_p95_seconds is not None
    assert result.grid.residual_p95_seconds > 0.035
    assert result.beats == beat_times


def test_estimate_uses_verified_local_checkpoint_without_model_download(
    tmp_path, monkeypatch
):
    checkpoint = tmp_path / "final0.ckpt"
    checkpoint.write_bytes(b"verified local checkpoint fixture")
    model_sha256 = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    beat_times = _beats(120.0, 60, 0.08)
    downbeat_times = _downbeats(beat_times, tuple(range(0, 60, 4)))
    constructor_arguments = {}

    class FakeFile2Beats:
        def __init__(self, *, checkpoint_path, device, dbn):
            constructor_arguments.update(
                checkpoint_path=checkpoint_path,
                device=device,
                dbn=dbn,
            )

        def __call__(self, audio_path):
            constructor_arguments["audio_path"] = audio_path
            return beat_times, downbeat_times

    monkeypatch.setattr(rhythm_engine, "get_model_path", lambda model_id: checkpoint)
    monkeypatch.setattr(rhythm_engine, "_load_file2beats", lambda: FakeFile2Beats)

    result = estimate_rhythm(
        "sample.wav",
        30.1,
        checkpoint,
        "final0",
        model_sha256,
        AnalysisSettings(),
    )

    assert constructor_arguments == {
        "checkpoint_path": str(checkpoint),
        "device": "cpu",
        "dbn": False,
        "audio_path": "sample.wav",
    }
    assert result.status == "reliable"
    assert result.beats == beat_times
    assert result.downbeats == downbeat_times


def test_estimate_rejects_checkpoint_digest_mismatch(tmp_path, monkeypatch):
    checkpoint = tmp_path / "final0.ckpt"
    checkpoint.write_bytes(b"verified local checkpoint fixture")
    monkeypatch.setattr(rhythm_engine, "get_model_path", lambda model_id: checkpoint)
    monkeypatch.setattr(
        rhythm_engine,
        "_load_file2beats",
        lambda: (_ for _ in ()).throw(AssertionError("inference must not start")),
    )

    result = estimate_rhythm(
        "sample.wav",
        30.1,
        checkpoint,
        "final0",
        "0" * 64,
        AnalysisSettings(),
    )

    assert result.status == "failed"
    assert result.reason == "provided model SHA-256 does not match the checkpoint"
