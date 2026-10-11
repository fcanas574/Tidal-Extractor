"""Independent, tuning-aware audio key and Camelot analysis."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from backend.analysis.types import (
    GridResult,
    KeyCandidate,
    KeyResult,
    RhythmResult,
    camelot_for_key,
)


_TARGET_SAMPLE_RATE = 22_050
_HOP_LENGTH = 512
_MINIMUM_WINDOW_SECONDS = 4.0
_MINIMUM_RMS_DBFS = -70.0
_MINIMUM_CHROMA_CV = 0.05
_MINIMUM_TOP_GAP = 0.10
_MINIMUM_WINNER_AGREEMENT = 0.60

_MAJOR_PROFILE = np.asarray(
    [5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0],
    dtype=np.float64,
)
_MINOR_PROFILE = np.asarray(
    [5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0],
    dtype=np.float64,
)
_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_PROFILES = tuple(
    (tonic_pc, mode, np.roll(base, tonic_pc))
    for tonic_pc in range(12)
    for mode, base in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE))
)


def _unknown(reason: str) -> KeyResult:
    return KeyResult(
        key=None,
        camelot=None,
        status="unknown",
        candidates=(),
        agreement=None,
        reason=reason,
    )


def _estimate_tuning(samples: np.ndarray, sample_rate: int) -> float | None:
    """Estimate one tuning offset for the decoded track."""
    try:
        import librosa

        tuning = float(librosa.estimate_tuning(y=samples, sr=sample_rate, resolution=0.01))
    except Exception:
        return None
    return tuning if math.isfinite(tuning) else None


def _extract_segment_chroma(
    segment: np.ndarray,
    *,
    sample_rate: int,
    tuning: float,
) -> np.ndarray | None:
    """Separate harmonic content and calculate CQT chroma for one segment."""
    try:
        import librosa

        harmonic = librosa.effects.harmonic(segment)
        return librosa.feature.chroma_cqt(
            y=harmonic,
            sr=sample_rate,
            hop_length=_HOP_LENGTH,
            tuning=tuning,
        )
    except Exception:
        return None


def _usable_beat_period(rhythm: RhythmResult | None) -> float | None:
    if rhythm is None:
        return None

    grid_period = rhythm.grid.period_seconds
    if isinstance(grid_period, (int, float)) and math.isfinite(grid_period) and grid_period > 0:
        if 16 * grid_period >= _MINIMUM_WINDOW_SECONDS:
            return float(grid_period)

    bpm = rhythm.bpm
    if isinstance(bpm, (int, float)) and math.isfinite(bpm) and bpm > 0:
        period = 60.0 / float(bpm)
        if math.isfinite(period) and 16 * period >= _MINIMUM_WINDOW_SECONDS:
            return period

    beat_times = rhythm.beats
    if len(beat_times) >= 2:
        intervals = np.diff(np.asarray(beat_times, dtype=np.float64))
        intervals = intervals[np.isfinite(intervals) & (intervals > 0)]
        if intervals.size:
            period = float(np.median(intervals))
            if 16 * period >= _MINIMUM_WINDOW_SECONDS:
                return period
    return None


def _reliable_bar_anchor(rhythm: RhythmResult | None, period: float | None) -> float | None:
    if rhythm is None or period is None:
        return None
    grid: GridResult = rhythm.grid
    if (
        grid.status != "reliable"
        or grid.meter != "4/4"
        or grid.origin_seconds is None
        or grid.first_downbeat_beat is None
        or not math.isfinite(grid.origin_seconds)
    ):
        return None
    return float(grid.origin_seconds + grid.first_downbeat_beat * period)


def _window_intervals(
    duration_seconds: float,
    rhythm: RhythmResult | None,
) -> tuple[tuple[float, float], ...]:
    period = _usable_beat_period(rhythm)
    if period is None:
        window_seconds, step_seconds, anchor = 8.0, 4.0, 0.0
    else:
        # Four bars in 4/4 (or 16 beats otherwise), advanced by two bars/eight beats.
        window_seconds, step_seconds = 16.0 * period, 8.0 * period
        anchor = _reliable_bar_anchor(rhythm, period) or 0.0

    if not math.isfinite(window_seconds) or not math.isfinite(step_seconds) or step_seconds <= 0:
        return ()

    start = anchor
    if start > 0:
        start -= math.ceil(start / step_seconds) * step_seconds
    intervals = []
    while start < duration_seconds:
        left = max(0.0, start)
        right = min(duration_seconds, start + window_seconds)
        if right - left >= _MINIMUM_WINDOW_SECONDS:
            intervals.append((left, right))
        start += step_seconds
    return tuple(intervals)


def _inverse_overlap_weights(intervals: Sequence[tuple[float, float]]) -> tuple[float, ...]:
    """Assign each window the duration it contributes after dividing overlap."""
    if not intervals:
        return ()
    weights = [0.0] * len(intervals)
    boundaries = sorted({point for interval in intervals for point in interval})
    for left, right in zip(boundaries, boundaries[1:]):
        duration = right - left
        if duration <= 0:
            continue
        midpoint = (left + right) / 2.0
        covering = [
            index
            for index, (start, end) in enumerate(intervals)
            if start <= midpoint < end
        ]
        if covering:
            contribution = duration / len(covering)
            for index in covering:
                weights[index] += contribution
    return tuple(weights)


def _normalized_chroma(raw_chroma: np.ndarray) -> np.ndarray | None:
    chroma = np.asarray(raw_chroma, dtype=np.float64)
    if chroma.ndim == 1:
        if chroma.shape != (12,):
            return None
        chroma = chroma[:, None]
    if chroma.ndim != 2 or chroma.shape[0] != 12 or chroma.shape[1] == 0:
        return None
    if not np.all(np.isfinite(chroma)):
        return None

    mean_chroma = np.maximum(np.mean(chroma, axis=1), 0.0)
    mean_value = float(np.mean(mean_chroma))
    if mean_value <= 0 or not math.isfinite(mean_value):
        return None
    coefficient_of_variation = float(np.std(mean_chroma) / mean_value)
    if not math.isfinite(coefficient_of_variation) or coefficient_of_variation < _MINIMUM_CHROMA_CV:
        return None
    return mean_chroma


def _centered_correlation(chroma: np.ndarray, profile: np.ndarray) -> float | None:
    centered_chroma = chroma - np.mean(chroma)
    centered_profile = profile - np.mean(profile)
    denominator = float(np.linalg.norm(centered_chroma) * np.linalg.norm(centered_profile))
    if denominator <= 0 or not math.isfinite(denominator):
        return None
    score = float(np.dot(centered_chroma, centered_profile) / denominator)
    return score if math.isfinite(score) else None


def _resample(samples: np.ndarray, source_rate: int) -> np.ndarray | None:
    if source_rate == _TARGET_SAMPLE_RATE:
        return samples
    try:
        import librosa

        result = librosa.resample(
            y=samples,
            orig_sr=source_rate,
            target_sr=_TARGET_SAMPLE_RATE,
        )
    except Exception:
        return None
    result = np.asarray(result, dtype=np.float32)
    if result.ndim != 1 or result.size == 0 or not np.all(np.isfinite(result)):
        return None
    return result


def _rms_dbfs(samples: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    if rms <= 0:
        return -math.inf
    return 20.0 * math.log10(rms)


def estimate_key(
    pcm: np.ndarray,
    sample_rate: int,
    rhythm: RhythmResult | None,
    duration_seconds: float,
) -> KeyResult:
    """Estimate key from mono PCM using segmented, tuning-aware harmonic chroma."""
    try:
        samples = np.asarray(pcm, dtype=np.float32)
    except (TypeError, ValueError):
        return _unknown("invalid_audio_samples")
    if samples.ndim != 1 or samples.size == 0:
        return _unknown("empty_or_non_mono_audio")
    if not np.all(np.isfinite(samples)):
        return _unknown("non_finite_audio_samples")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, (int, np.integer)) or sample_rate <= 0:
        return _unknown("invalid_sample_rate")
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not math.isfinite(duration_seconds)
        or duration_seconds <= 0
    ):
        return _unknown("invalid_duration")
    if _rms_dbfs(samples) < _MINIMUM_RMS_DBFS:
        return _unknown("audio_below_-70_dbfs")

    decoded_duration = min(float(duration_seconds), samples.size / float(sample_rate))
    resampled = _resample(samples, int(sample_rate))
    if resampled is None:
        return _unknown("audio_resampling_failed")
    tuning = _estimate_tuning(resampled, _TARGET_SAMPLE_RATE)
    if tuning is None:
        return _unknown("tuning_estimation_failed")

    intervals = _window_intervals(decoded_duration, rhythm)
    usable = []
    for start_seconds, end_seconds in intervals:
        start_sample = max(0, int(round(start_seconds * _TARGET_SAMPLE_RATE)))
        end_sample = min(resampled.size, int(round(end_seconds * _TARGET_SAMPLE_RATE)))
        segment = resampled[start_sample:end_sample]
        if segment.size == 0:
            continue
        raw_chroma = _extract_segment_chroma(
            segment,
            sample_rate=_TARGET_SAMPLE_RATE,
            tuning=tuning,
        )
        if raw_chroma is None:
            continue
        mean_chroma = _normalized_chroma(raw_chroma)
        if mean_chroma is None:
            continue
        scores = []
        for tonic_pc, mode, profile in _PROFILES:
            score = _centered_correlation(mean_chroma, profile)
            if score is not None:
                scores.append((tonic_pc, mode, score))
        if len(scores) == 24:
            ranked_scores = tuple(sorted(scores, key=lambda item: item[2], reverse=True))
            usable.append(((start_seconds, end_seconds), mean_chroma, tuple(scores), ranked_scores))

    if not usable:
        return _unknown("no_usable_tonal_windows")

    usable_intervals = tuple(item[0] for item in usable)
    weights = _inverse_overlap_weights(usable_intervals)
    total_weight = sum(weights)
    if total_weight <= 0 or not math.isfinite(total_weight):
        return _unknown("no_usable_tonal_windows")

    track_chroma = sum(
        (weight * item[1] for weight, item in zip(weights, usable)),
        start=np.zeros(12, dtype=np.float64),
    ) / total_weight
    track_mean = float(np.mean(track_chroma))
    if track_mean <= 0 or float(np.std(track_chroma) / track_mean) < _MINIMUM_CHROMA_CV:
        return _unknown("degenerate_track_chroma")

    aggregate_scores = []
    for candidate_index in range(24):
        tonic_pc, mode, _ = _PROFILES[candidate_index]
        weighted_score = sum(
            weight * item[2][candidate_index][2]
            for weight, item in zip(weights, usable)
        ) / total_weight
        aggregate_scores.append((tonic_pc, mode, float(weighted_score)))
    aggregate_scores.sort(key=lambda item: item[2], reverse=True)

    selected = aggregate_scores[0]
    winners_agreeing = sum(
        weight
        for weight, item in zip(weights, usable)
        if item[3][0][:2] == selected[:2]
    )
    agreement = float(winners_agreeing / total_weight)
    candidates = tuple(
        KeyCandidate(tonic_pc=tonic_pc, mode=mode, score=score)
        for tonic_pc, mode, score in aggregate_scores[:3]
    )

    review_reasons = []
    if len(usable) < 3:
        review_reasons.append("fewer_than_three_usable_windows")
    if aggregate_scores[0][2] - aggregate_scores[1][2] < _MINIMUM_TOP_GAP:
        review_reasons.append("top_two_gap_below_0.10")
    if agreement < _MINIMUM_WINNER_AGREEMENT:
        review_reasons.append("winner_agreement_below_0.60")

    tonic_pc, mode, _ = selected
    return KeyResult(
        key=f"{_NOTE_NAMES[tonic_pc]} {mode}",
        camelot=camelot_for_key(tonic_pc, mode),
        status="needs_review" if review_reasons else "reliable",
        candidates=candidates,
        agreement=agreement,
        reason=";".join(review_reasons) if review_reasons else None,
    )
