import json
import logging
import os
import subprocess
import sys
import tempfile
from functools import lru_cache

import numpy as np
from scipy.io import wavfile

logger = logging.getLogger(__name__)

WAVYPY_DIR = os.path.join(os.path.dirname(__file__), "wavypy")


class _AudioSegmentCompat:
    """Minimal pydub AudioSegment-compatible object using scipy data."""

    def __init__(self, sample_rate: int, samples: np.ndarray):
        self.frame_rate = sample_rate
        self.channels = samples.shape[1] if samples.ndim > 1 else 1
        self._samples = samples
        self.sample_width = 2  # s16le
        self._frame_count = len(samples)

    def frame_count(self) -> int:
        return self._frame_count

    def get_array_of_samples(self):
        return self._samples.flatten()

    def __len__(self):
        return int(self._frame_count / self.frame_rate * 1000)


def _run_wavypy(audio_path: str, output_path: str, band_preset: str, width: int) -> bool:
    """Run the wavypy wavy.py script via subprocess, patching pydub with scipy."""
    wavy_path = os.path.join(WAVYPY_DIR, "wavy.py")

    audioop_stub = os.path.join(os.path.dirname(__file__), "audioop_stub.py")
    code = f'''
import sys
sys.path.insert(0, {WAVYPY_DIR!r})
sys.path.insert(0, {os.path.dirname(audioop_stub)!r})

# Install audioop stub for Python 3.13+ before pydub imports
import audioop_stub
sys.modules["audioop"] = audioop_stub
sys.modules["pyaudioop"] = audioop_stub

import numpy as np
from scipy.io import wavfile

class FakeAudioSegment:
    def __init__(self, data, sample_width, frame_rate, channels):
        self._data = data.flatten()
        self.sample_width = sample_width
        self.frame_rate = frame_rate
        self.channels = channels
        self._frame_count = len(self._data) // channels
    def frame_count(self):
        return int(self._frame_count)
    def get_array_of_samples(self):
        return self._data
    def __len__(self):
        return int(self._frame_count / self.frame_rate * 1000)
    @staticmethod
    def from_file(filename):
        rate, data = wavfile.read(filename)
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        ch = int(data.shape[1]) if data.ndim > 1 else 1
        return FakeAudioSegment(data, 2, int(rate), ch)

import pydub
pydub.AudioSegment = FakeAudioSegment

# Now run wavy's main
from wavy import read_audio_file, generate_waveform_data, get_band_preset

bands = get_band_preset({band_preset!r})
audio = read_audio_file({audio_path!r}, show_info=False)

class _SF:
    def get_samples_per_pixel(self, sample_rate):
        return int(max(2, audio.frame_count() // {width}))

waveform = generate_waveform_data(
    audio, _SF(), False, bands,
    sample_format=0,  # BASE64_JSON
    compression=0,    # NONE
)
# save_as_json handles encode_samples + to_dict
waveform.save_as_json({output_path!r}, bits=2)  # 2 = SIXTEEN

# Reload and decode base64 to plain arrays for the frontend
import json as _json, base64 as _b64
with open({output_path!r}) as f:
    data = _json.load(f)

if data.get("type") == "multiband":
    for band in data["data"]["multiband"]["bands"]:
        raw = _b64.b64decode(band["samples"])
        band["samples"] = _json.loads(raw)

with open({output_path!r}, "w") as f:
    _json.dump(data, f)
'''

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": WAVYPY_DIR},
    )
    if result.returncode != 0:
        logger.error("wavypy failed (rc=%s): %s", result.returncode, result.stderr[:500])
        return False
    if result.stderr:
        logger.info("wavypy stderr: %s", result.stderr[:300])
    return True


def build_waveform(stream_url: str) -> dict:
    """Download audio, run wavypy with club preset, return waveform JSON."""
    tmp_audio = None
    tmp_json = None
    try:
        # Download full preview audio to temp WAV via ffmpeg
        tmp_audio_fd, tmp_audio = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_audio_fd)
        dl = subprocess.run([
            "ffmpeg", "-i", stream_url,
            "-ac", "1", "-ar", "44100",
            "-acodec", "pcm_s16le",
            "-loglevel", "error", "-y",
            tmp_audio,
        ], capture_output=True, timeout=60)
        if dl.returncode != 0 or os.path.getsize(tmp_audio) < 1000:
            logger.error("Download failed: %s", dl.stderr[:200])
            return {}

        # Run wavypy with "club" preset (3 bands, proper filter slopes)
        tmp_json_fd, tmp_json = tempfile.mkstemp(suffix=".json")
        os.close(tmp_json_fd)

        ok = _run_wavypy(tmp_audio, tmp_json, band_preset="club", width=600)
        if not ok:
            return {}

        with open(tmp_json) as f:
            data = json.load(f)

        logger.info("wavypy output type=%s, keys=%s", data.get("type"), list(data.keys()))
        if data.get("type") != "multiband":
            logger.error("wavypy returned non-multiband: %s", str(data)[:500])
            return {}

        bands_data = {}
        for band in data["data"]["multiband"]["bands"]:
            name = band["name"]
            samples = band.get("samples", [])
            if not samples:
                continue
            # Samples are [min0,max0,min1,max1,...] int16 pairs → compute RMS per pair
            points = len(samples) // 2
            rms = []
            for i in range(points):
                lo = samples[i * 2]
                hi = samples[i * 2 + 1]
                rms.append(abs(hi - lo) / 65536.0)
            # Normalize
            if rms:
                mx = max(rms)
                if mx > 0:
                    rms = [v / mx for v in rms]
            bands_data[name] = [round(v, 4) for v in rms]

        wf_duration = data.get("duration", 30)
        logger.info("wavypy waveform: %d points, duration=%.1fs, bands=%s",
                    len(bands_data.get("low", [])),
                    wf_duration,
                    list(bands_data.keys()))
        return {"bands": bands_data, "duration": wf_duration}

    except Exception as e:
        logger.error("wavypy waveform failed: %s", e)
        return {}
    finally:
        for p in (tmp_audio, tmp_json):
            if p and os.path.exists(p):
                os.unlink(p)


@lru_cache(maxsize=64)
def get_waveform_cached(stream_url: str) -> dict:
    colors = {"low": "#0055e2", "mid": "#f2aa3c", "high": "#ffffff"}
    result = build_waveform(stream_url)
    return {
        "bands": result.get("bands", {}),
        "colors": colors,
        "duration": result.get("duration", 30),
    }
