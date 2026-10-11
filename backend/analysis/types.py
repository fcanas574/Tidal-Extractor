"""Typed result and settings contracts for local preview analysis."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from typing import Literal, Mapping


KeyStatus = Literal["reliable", "needs_review", "unknown", "failed"]
GridStatus = Literal["reliable", "needs_review", "unavailable", "failed"]
RhythmStatus = Literal["reliable", "needs_review", "unavailable", "failed"]
AnalysisStatus = Literal["queued", "processing", "complete", "failed"]
PreviewStatus = Literal["queued", "processing", "partial", "complete", "failed"]


@dataclass(frozen=True)
class AnalysisSettings:
    model_id: str = "final0"
    key_profile_id: str = "temperley-2002-figure1-v1"
    key_sample_rate: int = 22050
    key_hop_length: int = 512
    tempo_minimum_beats: int = 32
    tempo_minimum_coverage: float = 0.5
    grid_p95_tolerance_seconds: float = 0.035
    grid_split_drift_tolerance_seconds: float = 0.040
    downbeat_minimum_events: int = 8
    downbeat_phase_agreement: float = 0.90
    downbeat_tolerance_seconds: float = 0.050
    schema_version: int = 1

    @property
    def canonical_json_bytes(self) -> bytes:
        """Return stable JSON bytes used to identify these result settings."""
        payload = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        return payload.encode("utf-8")

    @property
    def sha256(self) -> str:
        """Return the SHA-256 identity of the canonical settings JSON."""
        return sha256(self.canonical_json_bytes).hexdigest()


@dataclass(frozen=True)
class KeyCandidate:
    tonic_pc: int
    mode: str
    score: float


@dataclass(frozen=True)
class KeyResult:
    key: str | None
    camelot: str | None
    status: KeyStatus
    candidates: tuple[KeyCandidate, ...]
    agreement: float | None
    reason: str | None


@dataclass(frozen=True)
class GridResult:
    bpm: float | None
    period_seconds: float | None
    origin_seconds: float | None
    meter: str | None
    first_downbeat_beat: int | None
    status: GridStatus
    residual_p95_seconds: float | None
    split_drift_seconds: float | None
    reason: str | None


@dataclass(frozen=True)
class RhythmResult:
    bpm: float | None
    beats: tuple[float, ...]
    downbeats: tuple[float, ...]
    grid: GridResult
    status: RhythmStatus
    reason: str | None


@dataclass(frozen=True)
class HybridAnalysisResult:
    schema_version: int
    audio_fingerprint: str
    decoder_version: str
    duration_seconds: float
    model_id: str
    model_sha256: str
    key_profile_id: str
    settings_sha256: str
    key: KeyResult
    rhythm: RhythmResult


_CAMELOT_BY_KEY = {
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


def camelot_for_key(tonic_pc: int, mode: str) -> str:
    """Return the canonical Camelot code for a pitch class and mode."""
    try:
        return _CAMELOT_BY_KEY[(tonic_pc, mode)]
    except (KeyError, TypeError) as exc:
        raise ValueError("tonic_pc must be 0–11 and mode must be major or minor") from exc


def _validate_event_times(
    name: str, event_times: tuple[float, ...], duration_seconds: float
) -> None:
    previous = -math.inf
    for event_time in event_times:
        if not isinstance(event_time, (int, float)) or isinstance(event_time, bool):
            raise ValueError(f"{name} must contain finite numeric event times")
        if not math.isfinite(event_time):
            raise ValueError(f"{name} must contain finite numeric event times")
        if event_time < 0 or event_time > duration_seconds:
            raise ValueError(f"{name} event times must be within the audio duration")
        if event_time <= previous:
            raise ValueError(f"{name} event times must be strictly increasing")
        previous = event_time


def serialize_result(result: HybridAnalysisResult) -> dict[str, object]:
    """Convert a typed result to finite JSON data after validating event times."""
    duration = result.duration_seconds
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        raise ValueError("duration_seconds must be finite and non-negative")
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("duration_seconds must be finite and non-negative")

    _validate_event_times("beats", result.rhythm.beats, duration)
    _validate_event_times("downbeats", result.rhythm.downbeats, duration)

    try:
        json_text = json.dumps(asdict(result), allow_nan=False, separators=(",", ":"))
    except ValueError as exc:
        raise ValueError("analysis results cannot contain non-finite numbers") from exc
    return json.loads(json_text)


def deserialize_result(data: Mapping[str, object]) -> HybridAnalysisResult:
    """Restore and validate a result previously produced by serialize_result."""
    try:
        key_data = data["key"]
        rhythm_data = data["rhythm"]
        if not isinstance(key_data, Mapping) or not isinstance(rhythm_data, Mapping):
            raise ValueError("key and rhythm results must be JSON objects")

        grid_data = rhythm_data["grid"]
        if not isinstance(grid_data, Mapping):
            raise ValueError("grid result must be a JSON object")

        candidates_data = key_data["candidates"]
        if not isinstance(candidates_data, (list, tuple)):
            raise ValueError("key candidates must be a JSON array")
        candidates = tuple(KeyCandidate(**candidate) for candidate in candidates_data)
        key = KeyResult(
            key=key_data["key"],
            camelot=key_data["camelot"],
            status=key_data["status"],
            candidates=candidates,
            agreement=key_data["agreement"],
            reason=key_data["reason"],
        )
        grid = GridResult(**grid_data)
        rhythm = RhythmResult(
            bpm=rhythm_data["bpm"],
            beats=tuple(rhythm_data["beats"]),
            downbeats=tuple(rhythm_data["downbeats"]),
            grid=grid,
            status=rhythm_data["status"],
            reason=rhythm_data["reason"],
        )
        result = HybridAnalysisResult(
            schema_version=data["schema_version"],
            audio_fingerprint=data["audio_fingerprint"],
            decoder_version=data["decoder_version"],
            duration_seconds=data["duration_seconds"],
            model_id=data["model_id"],
            model_sha256=data["model_sha256"],
            key_profile_id=data["key_profile_id"],
            settings_sha256=data["settings_sha256"],
            key=key,
            rhythm=rhythm,
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid analysis result data") from exc

    serialize_result(result)
    return result
