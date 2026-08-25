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
