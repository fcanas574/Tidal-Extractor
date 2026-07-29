"""Stateful streaming waveform generation (Stage 2).

Mirrors the filtering and per-pixel min/max grouping of the existing full-file
wavypy path (``backend/waveform.py`` / ``backend/wavypy/wavy.py``) but does it
incrementally: PCM samples are fed in arbitrary chunks, scipy Butterworth SOS
filter state is carried across chunk boundaries via ``sosfilt``'s returned
``zf``, and only newly completed pixels are emitted from :meth:`feed`.

The band-filter specs are loaded from wavypy's real ``club`` preset so the SOS
sections are bit-identical to the existing analyzer -- we do not hand-duplicate
the cutoffs. The per-pixel metric and final per-band normalization match
``build_waveform`` exactly (``abs(max-min)/65536``, normalize by band max only
on completion), preserving the frontend contract consumed by
``AudioPlayerFooter.drawClubWaveform``.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

# Import wavypy's band presets without pulling in pydub/audioop at import time.
# wavypy only references those in read_audio_file(), which we never call here.
sys.path.insert(0, str(__import__("os").path.join(__import__("os").path.dirname(__file__), "wavypy")))
from wavy import get_band_preset, FilterType, FrequencyBand, FilterProfile  # noqa: E402

WAVEFORM_WIDTH = 600
SAMPLE_RATE = 44100
_CHANNELS = 1


def _club_frequency_bands(sample_rate: int) -> list[FrequencyBand]:
    """Return wavypy's parsed ``club`` FrequencyBand objects.

    ``get_band_preset`` already parses the preset table into FrequencyBand /
    FilterProfile objects (lowpass 250 / highpass 250 + lowpass 1200 /
    highpass 2000 + lowpass 3000, all order 2). We use them verbatim so the SOS
    sections are bit-identical to the existing analyzer -- the preset table in
    wavy.py is the single source of truth for the cutoff numbers. ``sample_rate``
    is accepted for API symmetry (the SOS sections are built per-profile later).
    """
    _ = sample_rate  # unused; kept for future per-rate scaling
    return list(get_band_preset("club"))


def club_bands(sample_rate: int) -> list[FrequencyBand]:
    """Public accessor for the club FrequencyBands (used by tests)."""
    return _club_frequency_bands(sample_rate)


@dataclass
class _BandState:
    """Per-band stateful filter + accumulator carried across chunks."""
    name: str
    sos_list: list[np.ndarray]          # one SOS section per cascaded profile
    zi_list: list[np.ndarray]           # carried filter state (same shape)
    remainder: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float64))
    points: list[float] = field(default_factory=list)  # raw per-pixel metric (unnormalized)

    def replace_zi(self, idx: int, zf: np.ndarray) -> None:
        """Update carried filter state for profile ``idx`` after a chunk."""
        self.zi_list[idx] = zf


class StreamingWaveformGenerator:
    """Accumulates tri-band min/max waveform pixels from streamed PCM chunks.

    Construct once per track. Call :meth:`feed` with successive int16-as-float
    sample chunks; it returns only the newly completed points per band.
    :meth:`finish` flushes any trailing complete pixel and finalizes the
    duration; :meth:`snapshot` returns the full ``{bands, duration, complete}``
    view, with per-band normalization applied once on completion (provisional
    snapshots return raw metrics -- see Global Constraint: do not normalize
    provisional points against a changing maximum).
    """

    def __init__(
        self,
        sample_rate: int,
        channels: int,
        total_samples: int,
        width: int,
        bands: list[FrequencyBand] | None = None,
    ):
        if channels != _CHANNELS:
            # The existing path mixes to mono in ffmpeg (-ac 1); streaming does
            # the same, so we only handle the mono case.
            raise ValueError(f"streaming generator expects mono input, got channels={channels}")
        self.sample_rate = sample_rate
        self.channels = channels
        self.total_samples = int(total_samples)
        self.width = int(width)
        self.samples_per_pixel = max(2, self.total_samples // self.width)
        self._fed_samples = 0
        self._complete = False

        band_specs = bands if bands is not None else _club_frequency_bands(sample_rate)
        self._band_states: dict[str, _BandState] = {
            b.name: self._init_band_state(b.name, b.filter_profiles)
            for b in band_specs
        }
        # Preserve declared band order for stable snapshot keys.
        self._band_order = [b.name for b in band_specs]

    @classmethod
    def from_samples(
        cls,
        samples: np.ndarray,
        width: int = WAVEFORM_WIDTH,
        sample_rate: int = SAMPLE_RATE,
        channels: int = _CHANNELS,
        chunk_sizes: Sequence[int] | None = None,
        band_preset: str = "club",
    ) -> "StreamingWaveformGenerator":
        """Convenience constructor: feed the whole signal (optionally chunked).

        Used by tests to compare chunked vs single-chunk output. The generator
        is returned finished (snapshot is complete).
        """
        samples = np.asarray(samples, dtype=np.float64)
        bands = _club_frequency_bands(sample_rate) if band_preset == "club" else None
        gen = cls(sample_rate, channels, len(samples), width, bands=bands)
        if chunk_sizes is None:
            gen.feed(samples)
        else:
            # Cycle through the chunk-size pattern until the whole signal is
            # consumed (the test feeds a full track in irregular chunks, not a
            # single pass whose sizes sum to less than the track length).
            i = 0
            k = 0
            n = len(samples)
            while i < n:
                sz = chunk_sizes[k % len(chunk_sizes)]
                gen.feed(samples[i:i + sz])
                i += sz
                k += 1
        gen.finish()
        return gen

    @staticmethod
    def _init_band_state(name: str, profiles: list[FilterProfile]) -> _BandState:
        sos_list: list[np.ndarray] = []
        zi_list: list[np.ndarray] = []
        for profile in profiles:
            nyquist = 0.5 * SAMPLE_RATE
            if isinstance(profile.cutoff_freq, tuple):
                normalized = (profile.cutoff_freq[0] / nyquist, profile.cutoff_freq[1] / nyquist)
            else:
                normalized = profile.cutoff_freq / nyquist
            btype = FilterType(profile.filter_type).name.lower()
            sos = butter(profile.order, normalized, btype=btype, output="sos")
            zi = sosfilt_zi(sos)
            if sos.ndim == 2 and sos.shape[0] == 1:
                zi = zi.reshape(1, 2)
            sos_list.append(sos)
            zi_list.append(zi)
        return _BandState(name=name, sos_list=sos_list, zi_list=zi_list)

    # -- core ----------------------------------------------------------------

    def feed(self, samples: np.ndarray) -> dict[str, list[float]]:
        """Feed one chunk of mono samples; return newly completed points.

        ``samples`` is signed-16-bit range mono PCM as float64 (filtering is
        done in float; the int cast happens at pixel-grouping time to match the
        existing wavypy path, which casts to int32 before clamping to int16).
        """
        if self._complete:
            raise RuntimeError("feed() called after finish()")
        samples = np.asarray(samples, dtype=np.float64).reshape(-1)
        self._fed_samples += len(samples)
        new_points: dict[str, list[float]] = {}
        for idx, name in enumerate(self._band_order):
            new_points[name] = self._feed_band(name, samples)
        return new_points

    def _feed_band(self, name: str, samples: np.ndarray) -> list[float]:
        state = self._band_states[name]
        filtered = samples
        # Cascade each filter profile, carrying state across chunks. wavypy
        # resets zi on every process_sample call because it only sees the whole
        # file at once; here we keep zf and feed it into the next sosfilt.
        for i, (sos, zi) in enumerate(zip(state.sos_list, state.zi_list)):
            filtered, zf = sosfilt(sos, filtered, zi=zi)
            state.zi_list[i] = zf
        combined = np.concatenate([state.remainder, filtered])
        spp = self.samples_per_pixel
        n_points = len(combined) // spp
        new: list[float] = []
        if n_points > 0:
            trimmed = combined[:n_points * spp]
            windows = trimmed.reshape(n_points, spp)
            # Match wavypy: int32 cast -> clamp to int16 -> per-window min/max.
            as_int = np.clip(windows.astype(np.int32), -32768, 32767)
            min_vals = as_int.min(axis=1)
            max_vals = as_int.max(axis=1)
            metric = np.abs(max_vals - min_vals) / 65536.0
            new = metric.tolist()
            state.points.extend(new)
            state.remainder = combined[n_points * spp:]
        else:
            state.remainder = combined
        return new

    def finish(self) -> dict[str, list[float]]:
        """Flush trailing complete pixel (sub-spp tail is dropped, matching
        wavypy), finalize duration, and mark the snapshot complete."""
        if self._complete:
            return {name: [] for name in self._band_order}
        new: dict[str, list[float]] = {}
        for name in self._band_order:
            state = self._band_states[name]
            spp = self.samples_per_pixel
            if len(state.remainder) >= spp:
                n = len(state.remainder) // spp
                trimmed = state.remainder[:n * spp]
                windows = trimmed.reshape(n, spp)
                as_int = np.clip(windows.astype(np.int32), -32768, 32767)
                metric = np.abs(as_int.max(axis=1) - as_int.min(axis=1)) / 65536.0
                state.points.extend(metric.tolist())
                new[name] = metric.tolist()
                state.remainder = state.remainder[n * spp:]
            else:
                # Sub-pixel tail: drop it (wavypy recurses until no points).
                state.remainder = np.empty(0, dtype=np.float64)
                new[name] = []
        self._complete = True
        return new

    def snapshot(self) -> dict:
        """Return ``{bands: {low, mid, high}, duration: float, complete: bool}``.

        Provisional (``complete=False``) snapshots return raw per-pixel metrics
        (unnormalized). The final (``complete=True``) snapshot normalizes each
        band by its own max, matching the existing ``build_waveform`` output
        that the frontend consumes.
        """
        bands: dict[str, list[float]] = {}
        for name in self._band_order:
            pts = list(self._band_states[name].points)
            if self._complete and pts:
                mx = max(pts)
                if mx > 0:
                    pts = [v / mx for v in pts]
            bands[name] = pts
        # Duration: once complete, base it on the declared total (the audio the
        # caller said it would stream) so a dropped sub-pixel tail doesn't
        # shorten the reported track length; pre-completion, use samples seen.
        if self._complete:
            seen = self.total_samples
        else:
            seen = self._fed_samples
        duration = seen / self.sample_rate
        return {"bands": bands, "duration": duration, "complete": self._complete}
