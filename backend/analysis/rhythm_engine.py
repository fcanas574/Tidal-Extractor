"""Beat event validation and conservative steady-grid fitting."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from math import ceil, isfinite
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

from scripts.setup_analysis_model import get_model_path

from .types import (
    AnalysisSettings,
    GridResult,
    GridStatus,
    RhythmResult,
    RhythmStatus,
)


def _valid_events(events: Iterable[float], duration_seconds: float) -> tuple[float, ...]:
    """Keep finite, in-range timestamps that remain strictly increasing."""
    valid: list[float] = []
    previous = -float("inf")
    for event in events:
        if isinstance(event, bool):
            continue
        try:
            timestamp = float(event)
        except (TypeError, ValueError, OverflowError):
            continue
        if not isfinite(timestamp) or timestamp < 0 or timestamp > duration_seconds:
            continue
        if timestamp <= previous:
            continue
        valid.append(timestamp)
        previous = timestamp
    return tuple(valid)


def _empty_grid(status: GridStatus, reason: str) -> GridResult:
    return GridResult(
        bpm=None,
        period_seconds=None,
        origin_seconds=None,
        meter=None,
        first_downbeat_beat=None,
        status=status,
        residual_p95_seconds=None,
        split_drift_seconds=None,
        reason=reason,
    )


def _result_without_grid(
    beats: tuple[float, ...],
    downbeats: tuple[float, ...],
    grid_status: GridStatus,
    rhythm_status: RhythmStatus,
    reason: str,
) -> RhythmResult:
    return RhythmResult(
        bpm=None,
        beats=beats,
        downbeats=downbeats,
        grid=_empty_grid(grid_status, reason),
        status=rhythm_status,
        reason=reason,
    )


def _candidate_period(intervals: Sequence[float], tolerance: float) -> float:
    """Choose the coarsest interval unit with the strongest robust support."""
    minimum = min(intervals)
    maximum = max(intervals)
    max_multiple = max(1, min(64, ceil(maximum / minimum) + 1))
    candidates: set[float] = set()
    for interval in intervals:
        for multiple in range(1, min(max_multiple, ceil(interval / minimum) + 1) + 1):
            candidate = interval / multiple
            if candidate > 0 and isfinite(candidate):
                candidates.add(candidate)

    best_period: float | None = None
    best_score: tuple[int, float, float] | None = None
    supported_periods: list[tuple[float, float]] = []
    for period in candidates:
        supported_residuals: list[float] = []
        supported = 0
        for interval in intervals:
            beat_count = max(1, round(interval / period))
            residual = abs(interval - beat_count * period)
            if residual <= tolerance:
                supported += 1
                supported_residuals.append(residual)
        typical_residual = (
            sum(supported_residuals) / supported if supported else float("inf")
        )
        if supported >= ceil(0.95 * len(intervals)):
            supported_periods.append((period, typical_residual))
        # This fallback is used only when no period has 95% interval support.
        # Prefer broad support and a tighter typical fit for diagnostics.
        score = (supported, -typical_residual, period)
        if best_score is None or score > best_score:
            best_period = period
            best_score = score

    if supported_periods:
        # At 95% support, choose the coarsest beat unit consistent with the
        # observed events. This avoids inventing faster beats to explain one
        # irregular interval while preserving genuine gaps as integer skips.
        best_period = max(period for period, _residual in supported_periods)
    if best_period is None:
        raise ValueError("could not infer a beat period")
    return best_period


def _alternative_has_event_support(
    intervals: Sequence[float],
    period: float,
    source_period: float,
    tolerance: float,
) -> bool:
    """Check whether events fit a neighboring octave as beats or subdivisions."""
    supported = 0
    for interval in intervals:
        beat_count = max(1, round(interval / period))
        matches_beat_or_gap = abs(interval - beat_count * period) <= tolerance
        subdivision_count = max(1, round(interval / source_period))
        matches_subdivision = period > source_period and abs(
            interval - subdivision_count * source_period
        ) <= tolerance
        if matches_beat_or_gap or matches_subdivision:
            supported += 1
    return supported >= ceil(0.95 * len(intervals))


def _octave_ambiguity_reason(
    intervals: Sequence[float],
    downbeats: Sequence[float],
    period: float,
    origin: float,
    settings: AnalysisSettings,
    tolerance: float,
) -> str | None:
    """Report octave alternatives supported by both beat and 4/4 phase evidence."""
    supported_tempos: list[float] = []
    for alternative_period in (period * 2.0, period / 2.0):
        if not _alternative_has_event_support(
            intervals, alternative_period, period, tolerance
        ):
            continue

        # A slower alternative may use either parity of the detected events as
        # its beat phase; a faster alternative may likewise start on either
        # newly inserted subdivision.
        alternate_origin = origin + min(period, alternative_period)
        if not any(
            _phase_result(downbeats, alternative_period, candidate_origin, settings)[0]
            == "4/4"
            for candidate_origin in (origin, alternate_origin)
        ):
            continue
        supported_tempos.append(60.0 / alternative_period)

    if not supported_tempos:
        return None

    tempos = sorted({60.0 / period, *supported_tempos})
    tempo_text = ", ".join(f"{tempo:.2f} BPM" for tempo in tempos)
    return (
        "possible half/double-tempo ambiguity among "
        f"{tempo_text}; review before accepting a fitted grid"
    )


def _robust_line_fit(
    beat_numbers: Sequence[int], event_times: Sequence[float]
) -> tuple[float, float, tuple[float, ...]]:
    """Fit event time to beat number with a Theil-Sen slope and median origin."""
    sample_positions = list(range(len(beat_numbers)))
    if len(sample_positions) > 256:
        sample_positions = [
            round(index * (len(beat_numbers) - 1) / 255) for index in range(256)
        ]

    slopes = [
        (event_times[right] - event_times[left])
        / (beat_numbers[right] - beat_numbers[left])
        for offset, left in enumerate(sample_positions)
        for right in sample_positions[offset + 1 :]
        if beat_numbers[right] > beat_numbers[left]
    ]
    period = median(slopes)
    origin = median(
        event_time - beat_number * period
        for beat_number, event_time in zip(beat_numbers, event_times)
    )
    residuals = tuple(
        event_time - (origin + beat_number * period)
        for beat_number, event_time in zip(beat_numbers, event_times)
    )
    return period, origin, residuals


def _percentile_95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, ceil(0.95 * len(ordered)) - 1)]


def _phase_result(
    downbeats: Sequence[float],
    period: float,
    origin: float,
    settings: AnalysisSettings,
) -> tuple[str | None, int | None, str | None]:
    if not downbeats:
        return None, None, "no downbeats were detected"

    phase_counts: Counter[int] = Counter()
    phase_beats: dict[int, list[int]] = {}
    for downbeat in downbeats:
        beat_number = round((downbeat - origin) / period)
        residual = abs(downbeat - (origin + beat_number * period))
        if residual <= settings.downbeat_tolerance_seconds:
            phase = beat_number % 4
            phase_counts[phase] += 1
            phase_beats.setdefault(phase, []).append(beat_number)

    if not phase_counts:
        return None, None, "no downbeats were within 50 ms of the fitted grid"

    phase, count = max(phase_counts.items(), key=lambda item: (item[1], -item[0]))
    agreement = count / len(downbeats)
    if count < settings.downbeat_minimum_events:
        return None, None, "4/4 phase needs at least eight grid-aligned downbeats"
    if agreement < settings.downbeat_phase_agreement:
        return None, None, "downbeats do not agree on one 4/4 phase at the required rate"
    return "4/4", min(phase_beats[phase]), None


def _fit_steady_grid(
    beats: Sequence[float],
    downbeats: Sequence[float],
    duration_seconds: float,
    settings: AnalysisSettings,
) -> RhythmResult:
    if isinstance(duration_seconds, bool):
        return _result_without_grid(
            (), (), "needs_review", "needs_review", "invalid source duration"
        )
    try:
        duration = float(duration_seconds)
    except (TypeError, ValueError, OverflowError):
        return _result_without_grid(
            (), (), "needs_review", "needs_review", "invalid source duration"
        )
    if not isfinite(duration) or duration <= 0:
        return _result_without_grid(
            (), (), "needs_review", "needs_review", "invalid source duration"
        )

    usable_beats = _valid_events(beats, duration)
    usable_downbeats = _valid_events(downbeats, duration)
    if len(usable_beats) < settings.tempo_minimum_beats:
        reason = (
            f"steady grid needs at least {settings.tempo_minimum_beats} usable beats; "
            f"received {len(usable_beats)}"
        )
        return _result_without_grid(
            usable_beats, usable_downbeats, "needs_review", "needs_review", reason
        )

    coverage = usable_beats[-1] - usable_beats[0]
    required_coverage = duration * settings.tempo_minimum_coverage
    if coverage < required_coverage:
        reason = "usable beats span less than half of the source"
        return _result_without_grid(
            usable_beats, usable_downbeats, "needs_review", "needs_review", reason
        )

    intervals = tuple(
        current - previous for previous, current in zip(usable_beats, usable_beats[1:])
    )
    interval_tolerance = settings.grid_p95_tolerance_seconds * 2
    candidate_period = _candidate_period(intervals, interval_tolerance)
    beat_numbers = [0]
    for interval in intervals:
        beat_numbers.append(beat_numbers[-1] + max(1, round(interval / candidate_period)))

    period, origin, signed_residuals = _robust_line_fit(beat_numbers, usable_beats)
    if period <= 0 or not isfinite(period) or not isfinite(origin):
        reason = "fitted beat period is invalid"
        return _result_without_grid(
            usable_beats, usable_downbeats, "needs_review", "needs_review", reason
        )

    absolute_residuals = tuple(abs(value) for value in signed_residuals)
    residual_p95 = _percentile_95(absolute_residuals)
    midpoint = len(signed_residuals) // 2
    early_median = median(signed_residuals[:midpoint])
    late_median = median(signed_residuals[midpoint:])
    split_drift = abs(late_median - early_median)

    if residual_p95 > settings.grid_p95_tolerance_seconds:
        reason = (
            f"grid 95th-percentile residual {residual_p95:.6f}s exceeds "
            f"{settings.grid_p95_tolerance_seconds:.3f}s"
        )
        return RhythmResult(
            bpm=None,
            beats=usable_beats,
            downbeats=usable_downbeats,
            grid=GridResult(
                bpm=None,
                period_seconds=None,
                origin_seconds=None,
                meter=None,
                first_downbeat_beat=None,
                status="needs_review",
                residual_p95_seconds=residual_p95,
                split_drift_seconds=split_drift,
                reason=reason,
            ),
            status="needs_review",
            reason=reason,
        )
    if split_drift > settings.grid_split_drift_tolerance_seconds:
        reason = (
            f"early/late median residual drift {split_drift:.6f}s exceeds "
            f"{settings.grid_split_drift_tolerance_seconds:.3f}s"
        )
        return RhythmResult(
            bpm=None,
            beats=usable_beats,
            downbeats=usable_downbeats,
            grid=GridResult(
                bpm=None,
                period_seconds=None,
                origin_seconds=None,
                meter=None,
                first_downbeat_beat=None,
                status="needs_review",
                residual_p95_seconds=residual_p95,
                split_drift_seconds=split_drift,
                reason=reason,
            ),
            status="needs_review",
            reason=reason,
        )

    ambiguity_reason = _octave_ambiguity_reason(
        intervals,
        usable_downbeats,
        period,
        origin,
        settings,
        interval_tolerance,
    )
    if ambiguity_reason is not None:
        return RhythmResult(
            bpm=60.0 / period,
            beats=usable_beats,
            downbeats=usable_downbeats,
            grid=GridResult(
                bpm=None,
                period_seconds=None,
                origin_seconds=None,
                meter=None,
                first_downbeat_beat=None,
                status="needs_review",
                residual_p95_seconds=residual_p95,
                split_drift_seconds=split_drift,
                reason=ambiguity_reason,
            ),
            status="needs_review",
            reason=ambiguity_reason,
        )

    meter, first_downbeat_beat, phase_reason = _phase_result(
        usable_downbeats, period, origin, settings
    )
    return RhythmResult(
        bpm=60.0 / period,
        beats=usable_beats,
        downbeats=usable_downbeats,
        grid=GridResult(
            bpm=60.0 / period,
            period_seconds=period,
            origin_seconds=origin,
            meter=meter,
            first_downbeat_beat=first_downbeat_beat,
            status="reliable",
            residual_p95_seconds=residual_p95,
            split_drift_seconds=split_drift,
            reason=phase_reason,
        ),
        status="reliable",
        reason=None,
    )


def fit_steady_grid(
    beats: Sequence[float],
    downbeats: Sequence[float],
    duration_seconds: float,
) -> RhythmResult:
    """Fit a steady beat grid without importing the inference runtime."""
    return _fit_steady_grid(beats, downbeats, duration_seconds, AnalysisSettings())


def _load_file2beats():
    """Import Beat This! only when inference is requested, leaving fitting lightweight."""
    from beat_this.inference import File2Beats

    return File2Beats


def _checkpoint_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as checkpoint:
        for chunk in iter(lambda: checkpoint.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimate_rhythm(
    audio_path: str,
    duration_seconds: float,
    model_path: Path,
    model_id: str,
    model_sha256: str,
    settings: AnalysisSettings,
) -> RhythmResult:
    """Run official Beat This! inference from a verified local checkpoint."""
    try:
        verified_path = get_model_path(model_id)
    except FileNotFoundError as exc:
        return _result_without_grid((), (), "unavailable", "unavailable", str(exc))
    except Exception as exc:
        return _result_without_grid(
            (), (), "failed", "failed", f"beat model validation failed: {exc}"
        )

    if Path(model_path).resolve() != Path(verified_path).resolve():
        reason = "provided model path does not match the verified local checkpoint"
        return _result_without_grid((), (), "failed", "failed", reason)
    if model_id != settings.model_id:
        reason = "requested model ID does not match analysis settings"
        return _result_without_grid((), (), "failed", "failed", reason)
    if len(model_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in model_sha256
    ):
        reason = "model SHA-256 must be a lowercase 64-character hexadecimal digest"
        return _result_without_grid((), (), "failed", "failed", reason)
    try:
        actual_sha256 = _checkpoint_sha256(Path(verified_path))
    except OSError as exc:
        return _result_without_grid(
            (), (), "failed", "failed", f"could not read verified checkpoint: {exc}"
        )
    if actual_sha256 != model_sha256:
        reason = "provided model SHA-256 does not match the checkpoint"
        return _result_without_grid((), (), "failed", "failed", reason)

    try:
        file2beats = _load_file2beats()(
            checkpoint_path=str(verified_path), device="cpu", dbn=False
        )
        beats, downbeats = file2beats(audio_path)
    except Exception as exc:
        return _result_without_grid(
            (), (), "failed", "failed", f"Beat This! inference failed: {exc}"
        )

    return _fit_steady_grid(beats, downbeats, duration_seconds, settings)
