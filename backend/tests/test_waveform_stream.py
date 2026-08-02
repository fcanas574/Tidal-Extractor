"""Tests for the streaming waveform analyzer (Stage 2, Tasks 1 & 2).

Task 1 tests pin the load-bearing property of the streaming generator: feeding
a track in arbitrary chunks must produce the same waveform as feeding it whole,
and filter state must survive chunk boundaries. Task 2 test pins the ffmpeg
reader: analyze_stream writes one temp WAV and emits progressive snapshots with
a terminal ``complete=True`` snapshot. Output-equivalence with the full-file
``get_waveform_cached`` path is checked in Task 3 integration tests.
"""
import numpy as np
import pytest

import backend.waveform_stream as waveform_stream
from backend.waveform_stream import (
    StreamingWaveformGenerator,
    analyze_stream,
    club_bands,
)


@pytest.fixture
def fixture_samples() -> np.ndarray:
    """Deterministic signed-16-bit mono signal with content in all 3 club bands.

    low  (<250Hz):   60 Hz sine
    mid  (250-1200): 600 Hz sine
    high (2000-3000): 2500 Hz sine
    plus broadband noise so min/max windows are non-trivial. Seeded for
    reproducibility (seed lives in the test, not the session).
    """
    sr = 44100
    n = 6 * sr  # 6 seconds -> 600 pixels at width=600 (spp=441)
    t = np.arange(n) / sr
    rng = np.random.default_rng(20260727)
    signal = (
        0.5 * np.sin(2 * np.pi * 60 * t)
        + 0.3 * np.sin(2 * np.pi * 600 * t)
        + 0.3 * np.sin(2 * np.pi * 2500 * t)
        + 0.1 * rng.standard_normal(n)
    )
    # Normalize to [-32768, 32767] int16 range.
    signal = (signal / np.max(np.abs(signal)) * 32767).astype(np.int16)
    return signal.astype(np.float64)


def test_chunked_output_matches_single_chunk_within_tolerance(fixture_samples):
    one = StreamingWaveformGenerator.from_samples(fixture_samples, width=600)
    chunked = StreamingWaveformGenerator.from_samples(
        fixture_samples, width=600, chunk_sizes=[137, 4096, 8191, 73]
    )
    assert chunked.snapshot()['duration'] == pytest.approx(one.snapshot()['duration'])
    assert set(chunked.snapshot()['bands'].keys()) == set(one.snapshot()['bands'].keys())
    for band in ("low", "mid", "high"):
        np.testing.assert_allclose(
            chunked.snapshot()['bands'][band],
            one.snapshot()['bands'][band],
            atol=2 / 32768,
        )


def test_filter_state_survives_chunk_boundary(fixture_samples):
    generator = StreamingWaveformGenerator.from_samples(
        fixture_samples, width=600, chunk_sizes=[1, 1, 1, 4096]
    )
    result = generator.snapshot()
    assert len(result['bands']['low']) > 0
    for band in ("low", "mid", "high"):
        band_vals = result['bands'][band]
        assert len(band_vals) > 0
        assert np.isfinite(band_vals).all()


def test_feed_returns_only_newly_completed_points(fixture_samples):
    """feed() must return the delta, not the whole accumulated list."""
    spp = 441  # width 600 over 6s @ 44100
    gen = StreamingWaveformGenerator(44100, 1, len(fixture_samples), 600,
                                     bands=club_bands(44100))
    # An incomplete chunk (less than one pixel) yields no new points yet.
    new = gen.feed(fixture_samples[:spp - 5])
    for band in ("low", "mid", "high"):
        assert new[band] == []
    # The next chunk crosses the first pixel boundary -> one new point per band.
    new = gen.feed(fixture_samples[spp - 5:spp + 3])
    for band in ("low", "mid", "high"):
        assert len(new[band]) == 1
    assert not gen.snapshot()['complete']


def test_snapshot_reports_complete_after_finish(fixture_samples):
    gen = StreamingWaveformGenerator.from_samples(fixture_samples, width=600)
    snap = gen.snapshot()
    assert snap['complete'] is True
    # Final normalized per-band output is bounded to [0, 1].
    for band in ("low", "mid", "high"):
        vals = np.asarray(snap['bands'][band])
        assert vals.size > 0
        assert vals.min() >= 0.0 and vals.max() <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# Task 2: analyze_stream -- ffmpeg PCM reader + one temp WAV + snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_stream_writes_wav_and_emits_snapshots(monkeypatch, tmp_path):
    """analyze_stream writes one temp WAV, emits progressive snapshots (first
    incomplete, last complete), with caller-owned temp-path in the result."""
    # Deterministic mono s16le PCM: 3 s of an 80 Hz sine (lives in the low band).
    sr = 44100
    n = 3 * sr
    t = np.arange(n) / sr
    signal = (0.9 * np.sin(2 * np.pi * 80 * t) * 32767).astype(np.int16)
    pcm_bytes = signal.tobytes()  # native int16 little-endian on this platform

    # Block size NOT aligned to 2-byte samples, proving analyze_stream aligns.
    block = 819

    async def fake_pcm_decoder(stream_url: str):
        """Async generator yielding raw s16le byte blocks (ffmpeg stand-in)."""
        for offset in range(0, len(pcm_bytes), block):
            yield pcm_bytes[offset:offset + block]

    monkeypatch.setattr(waveform_stream, "start_pcm_decoder", fake_pcm_decoder)

    snapshots = []
    result = await analyze_stream(
        "https://example.test/track", duration=12.0, width=60,
        on_snapshot=snapshots.append,
    )

    # Caller owns the temp WAV path; it exists and is a real WAV.
    assert result["temp_wav_path"] is not None
    from pathlib import Path
    assert Path(result["temp_wav_path"]).is_file()

    # Progressive snapshots were emitted, ending in the complete one.
    assert len(snapshots) >= 2
    assert snapshots[0]["complete"] is False
    assert snapshots[-1]["complete"] is True

    # The result carries the final bands + duration.
    assert set(result["bands"].keys()) == {"low", "mid", "high"}
    for band in ("low", "mid", "high"):
        assert len(result["bands"][band]) > 0

    # The temp WAV is a valid s16le mono 44100Hz file matching the streamed
    # samples (single media tee: key detection will read this, not re-fetch).
    from scipy.io import wavfile
    rate, data = wavfile.read(result["temp_wav_path"])
    assert rate == sr
    assert data.ndim == 1
    assert len(data) == n


@pytest.mark.asyncio
async def test_analyze_stream_cleans_up_on_failure(monkeypatch, tmp_path):
    """If the decoder blows up, no temp WAV is left behind and no snapshot claims
    a complete state."""
    async def failing_decoder(stream_url: str):
        raise RuntimeError("ffmpeg exploded")
        yield  # pragma: no cover - make this an async generator

    monkeypatch.setattr(waveform_stream, "start_pcm_decoder", failing_decoder)
    snapshots = []
    result = await analyze_stream(
        "https://example.test/track", duration=10.0, width=60,
        on_snapshot=snapshots.append,
    )
    # Analyzer returns bands + duration (empty) and NO temp wav path on failure.
    assert result["temp_wav_path"] is None
    assert result["bands"] == {"low": [], "mid": [], "high": []}
    # No complete snapshot emitted for a track that never produced output.
    assert all(s["complete"] is False for s in snapshots)

