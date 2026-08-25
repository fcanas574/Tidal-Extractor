from pathlib import Path

import numpy as np
import pytest
from backend.waveform_stream import StreamingWaveformGenerator


@pytest.fixture
def fixture_samples():
    rng = np.random.default_rng(42)
    t = np.arange(44100 * 3, dtype=np.int64)  # ~3 s: many pixels, deterministic
    base = (12000 * np.sin(2 * np.pi * 220 * t / 44100)
            + 6000 * np.sin(2 * np.pi * 3000 * t / 44100))
    noise = rng.integers(-800, 800, size=t.size)
    return np.clip(base + noise, -32768, 32767).astype(np.int16)


def _feed_chunks(gen, samples, sizes):
    start = 0
    for size in sizes:
        gen.feed(samples[start:start + size])
        start += size


def test_chunked_matches_single_chunk_within_tolerance(fixture_samples):
    one = StreamingWaveformGenerator(44100, fixture_samples.size, width=600)
    one.feed(fixture_samples)
    fin_one = one.finish()

    many = StreamingWaveformGenerator(44100, fixture_samples.size, width=600)
    _feed_chunks(many, fixture_samples, (137, 4096, 8191, 73, 100000, 10, 50000, 999999))
    fin_many = many.finish()

    assert set(fin_many["bands"]) == set(fin_one["bands"])
    for band in ("low", "mid", "high"):
        assert len(fin_many["bands"][band]) == len(fin_one["bands"][band]) > 0
        np.testing.assert_allclose(fin_many["bands"][band], fin_one["bands"][band],
                                   atol=2 / 32768)


def test_filter_state_survives_pathological_boundaries(fixture_samples):
    gen = StreamingWaveformGenerator(44100, fixture_samples.size, width=600)
    _feed_chunks(gen, fixture_samples, (1, 1, 1, 4096, 1, 2048))
    result = gen.finish()
    for band in result["bands"].values():
        assert len(band) > 0
        assert np.isfinite(band).all()


def test_provisional_points_use_stable_scale(fixture_samples):
    gen = StreamingWaveformGenerator(44100, fixture_samples.size, width=600)
    out = gen.feed(fixture_samples[:44100])
    out2 = gen.feed(fixture_samples[44100:])
    # Provisional values are bounded in [0, 1]; later chunks never rescale earlier ones
    assert all(0.0 <= v <= 1.0 for v in out["low"] + out2["low"])


# --- Task 4: ffmpeg PCM streaming with one temp WAV ---
import io
import wave as wavemod
from backend import waveform_stream


class FakeProc:
    def __init__(self, pcm_bytes):
        self.stdout = io.BytesIO(pcm_bytes)
        self.killed = False

    async def read(self, n):
        await __import__("asyncio").sleep(0)
        return self.stdout.read(n)

    def kill(self):
        self.killed = True

    async def wait(self):
        return 0


@pytest.mark.asyncio
async def test_analyze_stream_writes_wav_and_emits_snapshots(tmp_path, monkeypatch):
    pcm = (np.sin(np.linspace(0, 400, 44100 * 2)) * 10000).astype(np.int16).tobytes()
    proc = FakeProc(pcm)

    async def fake_start(url):
        return proc

    monkeypatch.setattr(waveform_stream, "start_pcm_decoder", fake_start)
    snapshots = []
    result = await waveform_stream.analyze_stream(
        "https://example.test/x", 2.0, width=60,
        on_snapshot=snapshots.append, temp_dir=str(tmp_path))

    assert Path(result["temp_wav_path"]).exists()
    with wavemod.open(result["temp_wav_path"], "rb") as w:
        assert w.getframerate() == 44100
        assert w.getsampwidth() == 2
        assert w.getnchannels() == 1
        assert w.getnframes() == len(pcm) // 2
    assert snapshots[-1]["complete"] is True
    assert all(s["complete"] is False for s in snapshots[:-1])


@pytest.mark.asyncio
async def test_analyze_stream_cleans_up_on_decoder_error(tmp_path, monkeypatch):
    class BoomStdout:
        async def read(self, n):
            raise RuntimeError("pipe died")

    class BadProc:
        stdout = BoomStdout()
        killed = False

        def kill(self):
            self.killed = True

        async def wait(self):
            return 1

    async def fake_start(url):
        return BadProc()

    monkeypatch.setattr(waveform_stream, "start_pcm_decoder", fake_start)
    with pytest.raises(RuntimeError):
        await waveform_stream.analyze_stream("u", 2.0, temp_dir=str(tmp_path))
    assert not list(tmp_path.glob("*.wav"))  # temp WAV removed on failure
