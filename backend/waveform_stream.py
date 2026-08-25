"""Stateful streaming waveform generation compatible with wavypy band presets."""
import os
import sys

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "wavypy"))
from wavy import FilterType, get_band_preset  # noqa: E402


class StreamingWaveformGenerator:
    """Chunked min/max waveform generator preserving filter state across feeds."""

    def __init__(self, sample_rate: int, total_samples: int, width: int = 600,
                 preset: str = "club"):
        self.sample_rate = sample_rate
        self.total_samples = total_samples
        self.samples_per_pixel = max(2, total_samples // width)
        self.bands = get_band_preset(preset)
        self._filters: dict = {}          # key -> [sos, zi]  (zi mutated in place)
        self._remainder_store: dict = {}  # band name -> unprocessed filtered tail
        self._points: dict = {b.name: [] for b in self.bands}
        self._consumed = 0

    def _create_filter(self, profile):
        nyquist = 0.5 * self.sample_rate
        cut = profile.cutoff_freq
        normalized = ((cut[0] / nyquist, cut[1] / nyquist)
                      if isinstance(cut, tuple) else cut / nyquist)
        btype = FilterType(profile.filter_type).name.lower()
        sos = butter(profile.order, normalized, btype=btype, output="sos")
        zi = sosfilt_zi(sos)
        if sos.ndim == 2 and sos.shape[0] == 1:
            zi = zi.reshape(1, 2)
        return sos, zi

    def feed(self, samples: np.ndarray) -> dict:
        newly = {name: [] for name in self._points}
        if samples.size == 0:
            return newly
        x = samples.astype(np.float64)
        for band in self.bands:
            y = x
            for profile in band.filter_profiles:
                key = (band.name, id(profile))
                if key not in self._filters:
                    self._filters[key] = self._create_filter(profile)
                sos, zi = self._filters[key]
                y, zf = sosfilt(sos, y, zi=zi.copy())
                self._filters[key] = [sos, zf]  # carry filter state across chunks
            buf = self._remainder_store.get(band.name)
            buf = y if buf is None or buf.size == 0 else np.concatenate([buf, y])
            complete_pts = buf.size // self.samples_per_pixel
            if complete_pts:
                usable = buf[: complete_pts * self.samples_per_pixel]
                self._remainder_store[band.name] = buf[complete_pts * self.samples_per_pixel:]
                windows = usable.reshape(complete_pts, self.samples_per_pixel)
                amps = (np.abs(windows.max(axis=1) - windows.min(axis=1)) / 65536.0)
                self._points[band.name].extend(amps.tolist())
                newly[band.name] = amps.tolist()
            else:
                self._remainder_store[band.name] = buf
        self._consumed += samples.size
        return newly

    def snapshot(self, complete: bool = False) -> dict:
        dur = self._consumed / self.sample_rate if self.sample_rate else 0.0
        return {"bands": {k: list(v) for k, v in self._points.items()},
                "duration": dur, "complete": complete}

    def finish(self) -> dict:
        for band in self.bands:
            rem = self._remainder_store.pop(band.name, None)
            if rem is not None and rem.size >= self.samples_per_pixel // 2:
                pts = rem.size // self.samples_per_pixel
                if pts:
                    windows = rem[: pts * self.samples_per_pixel].reshape(pts, self.samples_per_pixel)
                    amps = (np.abs(windows.max(axis=1) - windows.min(axis=1)) / 65536.0).tolist()
                    self._points[band.name].extend(amps)
                    rem = rem[pts * self.samples_per_pixel:]
            self._remainder_store[band.name] = rem if rem is not None else np.empty(0)
        out = {}
        for name, vals in self._points.items():
            mx = max(vals) if vals else 0.0
            out[name] = [v / mx for v in vals] if mx > 0 else list(vals)
        return {"bands": out,
                "duration": self._consumed / self.sample_rate,
                "complete": True}


# --- Task 4: ffmpeg PCM streaming with one temp WAV ---
import asyncio
import contextlib
import inspect
import os
import tempfile
import wave

FFMPEG_CMD = ["ffmpeg", "-i", "{url}", "-ac", "1", "-ar", "44100",
              "-f", "s16le", "-acodec", "pcm_s16le", "-loglevel", "error", "pipe:1"]
READ_BYTES = 44100 * 2 * 2  # ~1 second of mono s16 audio per read
READ_TIMEOUT_S = 30         # kill ffmpeg if no PCM arrives for 30s (stall guard)


async def start_pcm_decoder(stream_url: str):
    cmd = [c.format(url=stream_url) if "{url}" in c else c for c in FFMPEG_CMD]
    return await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)


async def _emit(on_snapshot, snap):
    """Support both sync and async snapshot callbacks."""
    res = on_snapshot(snap)
    if inspect.isawaitable(res):
        await res


async def _read_block(proc):
    """Read one PCM block, tolerating sync (fake/test) or async (real) readers."""
    res = proc.stdout.read(READ_BYTES)
    if inspect.isawaitable(res):
        return await asyncio.wait_for(res, timeout=READ_TIMEOUT_S)
    return res


async def analyze_stream(stream_url, duration, width=600, on_snapshot=None,
                         temp_dir=None, sample_rate=44100):
    fd, wav_path = tempfile.mkstemp(suffix=".wav", dir=temp_dir)
    os.close(fd)
    try:
        proc = await start_pcm_decoder(stream_url)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(wav_path)
        raise
    fallback_total = sample_rate * 60 * 30  # 30-minute ceiling keeps pixels stable if duration unknown
    total = int(duration * sample_rate) if duration else fallback_total
    gen = StreamingWaveformGenerator(sample_rate, total, width=width)
    consumed = 0
    next_snapshot_at = sample_rate  # publish at most once per second of audio
    try:
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            while True:
                try:
                    block = await _read_block(proc)
                except asyncio.TimeoutError:
                    raise RuntimeError("ffmpeg stalled: no PCM for 30s")
                if not block:
                    break
                if len(block) % 2:
                    block = block[:-1]
                w.writeframes(block)
                samples = np.frombuffer(block, dtype=np.int16)
                consumed += samples.size
                gen.feed(samples)
                if on_snapshot and consumed >= next_snapshot_at:
                    next_snapshot_at = consumed + sample_rate
                    await _emit(on_snapshot, gen.snapshot(complete=False))
        rc = await proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg exited {rc}")
        final = gen.finish()
        final["duration"] = consumed / sample_rate
        final["temp_wav_path"] = wav_path
        if on_snapshot:
            await _emit(on_snapshot, final)
        return final
    except BaseException:
        proc.kill()
        with contextlib.suppress(ProcessLookupError):
            await proc.wait()
        with contextlib.suppress(OSError):
            os.unlink(wav_path)
        raise
