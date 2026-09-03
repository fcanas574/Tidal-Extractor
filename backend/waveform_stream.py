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

import asyncio
import logging
import os
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Sequence

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


# ---------------------------------------------------------------------------
# Task 2: ffmpeg PCM streaming + one temp WAV + progressive snapshots
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# Subprocess read deadline; matches the existing build_waveform timeout.
_PCM_TIMEOUT = 60
# Emit a snapshot after this many new complete pixels accumulate.
_SNAPSHOT_INTERVAL_PIXELS = 50


async def start_pcm_decoder(stream_url: str) -> AsyncIterator[bytes]:
    """Launch ffmpeg and yield raw s16le mono PCM byte blocks from stdout.

    Mirrors the existing ffmpeg command (``-ac 1 -ar 44100 -acodec pcm_s16le``)
    but streams stdout instead of writing to a file. Blocks need NOT be aligned
    to 2-byte samples --
    ``analyze_stream`` aligns them. On cancellation/timeout the subprocess is
    terminated and waited on.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", stream_url,
        "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-loglevel", "error", "pipe:1",
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        assert proc.stdout is not None
        while True:
            block = await asyncio.wait_for(proc.stdout.read(8192), _PCM_TIMEOUT)
            if not block:
                break
            yield block
        await asyncio.wait_for(proc.wait(), _PCM_TIMEOUT)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        with suppress_called_process_error():
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                proc.kill()
                with suppress_called_process_error():
                    await proc.wait()
        raise
    finally:
        if proc.returncode is None:
            with suppress_called_process_error():
                proc.kill()
                await proc.wait()


class _SuppressCalledProcessError:
    """contextlib.suppress that also tolerates ProcessLookupError (race where the
    subprocess already exited). Kept tiny to avoid an extra import alias."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            return False
        return issubclass(exc_type, (ProcessLookupError,))


def suppress_called_process_error() -> _SuppressCalledProcessError:
    return _SuppressCalledProcessError()


async def _emit(callback: Callable[[dict], Any] | None, snapshot: dict) -> None:
    """Invoke the snapshot callback, awaiting it if it returns a coroutine.

    Accepts both the plan's sync ``list.append`` and an async callback.
    """
    if callback is None:
        return
    result = callback(snapshot)
    if isinstance(result, Awaitable):
        await result


async def analyze_stream(
    stream_url: str,
    duration: float | None,
    width: int = WAVEFORM_WIDTH,
    on_snapshot: Callable[[dict], Any] | None = None,
) -> dict[str, Any]:
    """Stream one preview track from ``stream_url`` into tri-band waveform
    analysis, writing a single temp WAV that callers reuse for key/BPM
    detection (no second network request).

    Emits progressive ``{bands, duration, complete}`` snapshots via
    ``on_snapshot`` (first incomplete, last complete). Returns the final
    ``{bands: {low, mid, high}, duration: float, temp_wav_path: str | None}``;
    the caller owns deletion of the temp WAV after key analysis.

    On any failure, returns empty bands with ``temp_wav_path=None`` and no temp
    file left on disk -- audio playback (started independently elsewhere) is not
    interrupted.
    """
    # Derive total samples for the streaming generator's samples_per_pixel.
    if duration is not None and duration > 0:
        total_samples = int(duration * SAMPLE_RATE)
    else:
        total_samples = 0  # generator falls back to max(2, 0//width)=2; refined after first chunk
    gen = StreamingWaveformGenerator(SAMPLE_RATE, _CHANNELS, total_samples, width)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="preview_stream_")
    os.close(tmp_fd)
    wav_writer: wave.Wave_write | None = None
    try:
        wav_writer = wave.open(tmp_path, "wb")
        wav_writer.setnchannels(_CHANNELS)
        wav_writer.setsampwidth(2)  # s16le
        wav_writer.setframerate(SAMPLE_RATE)

        saw_samples = 0
        pending_new = 0
        carry = b""  # trailing odd byte from a split read, prepended next block
        async for block in start_pcm_decoder(stream_url):
            block = carry + block
            # Align to a 2-byte sample boundary; carry the leftover byte forward
            # rather than dropping it (ffmpeg emits whole samples, but a read()
            # can split a frame across blocks).
            overflow = len(block) % 2
            if overflow:
                carry = block[-1:]
                block = block[:-1]
            else:
                carry = b""
            if not block:
                continue
            wav_writer.writeframes(block)
            samples = np.frombuffer(block, dtype="<i2").astype(np.float64)
            saw_samples += len(samples)
            new = gen.feed(samples)
            # Emit a progressive snapshot whenever new complete pixels land,
            # throttled so short tracks emit at least one mid-stream snapshot
            # and long tracks do not flood the callback per read block.
            pending_new += sum(len(v) for v in new.values())
            if pending_new >= _SNAPSHOT_INTERVAL_PIXELS or any(new.values()):
                pending_new = 0
                await _emit(on_snapshot, gen.snapshot())
        # Flush any final odd byte (ffmpeg always emits whole samples, so this
        # is empty in practice -- a single trailing byte is not a sample).
        _ = carry

        # If duration was unknown, refine total so finish()/snapshot report the
        # real length rather than the empty-string fallback of 2 samples/pixel.
        if total_samples == 0 and saw_samples > 0:
            gen.total_samples = saw_samples
            # samples_per_pixel stays as-is (already set from width/total before
            # any feeding); we only correct the reported duration via total.

        gen.finish()
        await _emit(on_snapshot, gen.snapshot())
        final = gen.snapshot()
        return {
            "bands": final["bands"],
            "duration": final["duration"],
            "temp_wav_path": tmp_path,
        }
    except Exception as exc:  # pragma: no cover - exercised by failure test
        logger.warning("analyze_stream failed for %s: %s", stream_url, exc)
        # Clean up the temp WAV on failure -- caller gets no path to own.
        _safe_unlink(tmp_path)
        return {"bands": {"low": [], "mid": [], "high": []}, "duration": float(duration or 0), "temp_wav_path": None}
    finally:
        if wav_writer is not None:
            with suppress_called_process_error():
                wav_writer.close()


def _safe_unlink(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError:
        logger.debug("could not remove temp wav %s", path, exc_info=True)
