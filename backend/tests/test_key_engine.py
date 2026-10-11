import numpy as np
import pytest

from backend.analysis import key_engine
from backend.analysis.key_engine import estimate_key


SAMPLE_RATE = 22_050
MAJOR_PROFILE = np.array(
    [5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0]
)
MINOR_PROFILE = np.array(
    [5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0]
)
CANONICAL_NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _profile(tonic_pc: int, mode: str) -> np.ndarray:
    base = MAJOR_PROFILE if mode == "major" else MINOR_PROFILE
    return np.roll(base, tonic_pc)


def _audio(duration_seconds: float = 20.0) -> np.ndarray:
    times = np.arange(int(SAMPLE_RATE * duration_seconds)) / SAMPLE_RATE
    return (0.2 * np.sin(2 * np.pi * 220 * times)).astype(np.float32)


def _set_chroma(monkeypatch, chroma_for_segment):
    tuning_calls = []
    tuning_offsets = []

    def estimate_tuning(samples, sample_rate):
        tuning_calls.append((len(samples), sample_rate))
        return 0.0

    def extract_chroma(segment, *, sample_rate, tuning):
        tuning_offsets.append(tuning)
        chroma = np.asarray(chroma_for_segment(segment), dtype=np.float64)
        return np.repeat(chroma[:, None], 24, axis=1)

    monkeypatch.setattr(key_engine, "_estimate_tuning", estimate_tuning)
    monkeypatch.setattr(key_engine, "_extract_segment_chroma", extract_chroma)
    return tuning_calls, tuning_offsets


def test_profile_rotation_recovers_every_tonic_and_mode(monkeypatch):
    active_profile = [MAJOR_PROFILE]
    _set_chroma(monkeypatch, lambda _: active_profile[0])

    for tonic_pc in range(12):
        for mode in ("major", "minor"):
            active_profile[0] = _profile(tonic_pc, mode)
            result = estimate_key(_audio(), SAMPLE_RATE, None, 20.0)

            assert result.key == f"{CANONICAL_NOTES[tonic_pc]} {mode}"
            assert result.candidates[0].tonic_pc == tonic_pc
            assert result.candidates[0].mode == mode


def test_camelot_mapping_and_enharmonics(monkeypatch):
    active_profile = [_profile(0, "major")]
    _set_chroma(monkeypatch, lambda _: active_profile[0])

    c_major = estimate_key(_audio(), SAMPLE_RATE, None, 20.0)
    active_profile[0] = _profile(9, "minor")
    a_minor = estimate_key(_audio(), SAMPLE_RATE, None, 20.0)

    assert (c_major.key, c_major.camelot) == ("C major", "8B")
    assert (a_minor.key, a_minor.camelot) == ("A minor", "8A")

    # Enharmonic spellings share a pitch class; results use one canonical spelling.
    for alias, tonic_pc, mode, expected in (
        ("C#", 1, "major", ("C# major", "3B")),
        ("Db", 1, "major", ("C# major", "3B")),
        ("D#", 3, "minor", ("D# minor", "2A")),
        ("Eb", 3, "minor", ("D# minor", "2A")),
        ("E#", 5, "major", ("F major", "7B")),
        ("F", 5, "major", ("F major", "7B")),
        ("F#", 6, "major", ("F# major", "2B")),
        ("Gb", 6, "major", ("F# major", "2B")),
        ("G#", 8, "minor", ("G# minor", "1A")),
        ("Ab", 8, "minor", ("G# minor", "1A")),
        ("A#", 10, "major", ("A# major", "6B")),
        ("Bb", 10, "major", ("A# major", "6B")),
        ("B#", 0, "major", ("C major", "8B")),
        ("C", 0, "major", ("C major", "8B")),
        ("Cb", 11, "minor", ("B minor", "10A")),
        ("B", 11, "minor", ("B minor", "10A")),
        ("Fb", 4, "major", ("E major", "12B")),
        ("E", 4, "major", ("E major", "12B")),
    ):
        active_profile[0] = _profile(tonic_pc, mode)
        result = estimate_key(_audio(), SAMPLE_RATE, None, 20.0)
        assert (result.key, result.camelot) == expected, alias


@pytest.mark.parametrize("chroma_kind", ["silence", "flat", "empty", "nonfinite"])
def test_silence_flat_and_nonfinite_chroma_are_unknown(monkeypatch, chroma_kind):
    if chroma_kind == "silence":
        pcm = np.zeros(SAMPLE_RATE * 20, dtype=np.float32)
    elif chroma_kind == "nonfinite":
        pcm = _audio()
        pcm[10] = np.nan
    else:
        pcm = _audio()

    chroma = {
        "flat": np.ones(12),
        "empty": np.empty((12, 0)),
        "nonfinite": np.full(12, np.nan),
        "silence": MAJOR_PROFILE,
    }[chroma_kind]
    _set_chroma(monkeypatch, lambda _: chroma)

    result = estimate_key(pcm, SAMPLE_RATE, None, 20.0)

    assert result.status == "unknown"
    assert result.key is None
    assert result.camelot is None
    assert all(np.isfinite(candidate.score) for candidate in result.candidates)
    assert result.agreement is None or np.isfinite(result.agreement)


def test_tuning_offset_is_estimated_once_and_applied_to_each_segment(monkeypatch):
    tuning_calls = []
    tuning_offsets = []

    def estimate_tuning(samples, sample_rate):
        tuning_calls.append((len(samples), sample_rate))
        return 0.37

    def extract_chroma(segment, *, sample_rate, tuning):
        tuning_offsets.append(tuning)
        return np.repeat(_profile(0, "major")[:, None], 24, axis=1)

    monkeypatch.setattr(key_engine, "_estimate_tuning", estimate_tuning)
    monkeypatch.setattr(key_engine, "_extract_segment_chroma", extract_chroma)

    result = estimate_key(_audio(), SAMPLE_RATE, None, 20.0)

    assert result.key == "C major"
    assert len(tuning_calls) == 1
    assert len(tuning_offsets) == 5
    assert tuning_offsets == [0.37] * 5


def test_fewer_than_three_usable_windows_requires_review(monkeypatch):
    _set_chroma(monkeypatch, lambda _: _profile(4, "minor"))

    result = estimate_key(_audio(11.9), SAMPLE_RATE, None, 11.9)

    assert result.key == "E minor"
    assert result.status == "needs_review"
    assert "three" in result.reason


def test_conflicting_segment_winners_require_review(monkeypatch):
    pcm = _audio(24.0)
    for start_seconds in (0, 4, 8):
        pcm[int(start_seconds * SAMPLE_RATE)] = 0.8
    for start_seconds in (12, 16, 20):
        pcm[int(start_seconds * SAMPLE_RATE)] = 0.9

    def chroma_for_segment(segment):
        return _profile(0, "major") if segment[0] < 0.85 else _profile(7, "major")

    _set_chroma(monkeypatch, chroma_for_segment)

    result = estimate_key(pcm, SAMPLE_RATE, None, 24.0)

    assert result.key == "C major"
    assert result.status == "needs_review"
    assert result.agreement < 0.60


def test_overlapping_windows_use_inverse_overlap_duration_weights():
    weights = key_engine._inverse_overlap_weights(((0.0, 8.0), (4.0, 12.0), (8.0, 12.0)))

    assert weights == pytest.approx((6.0, 4.0, 2.0))
    assert sum(weights) == pytest.approx(12.0)
