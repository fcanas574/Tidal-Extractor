"""Tests for the stateful streaming waveform generator (Stage 2, Task 1).

These tests pin the load-bearing property of the streaming analyzer: feeding a
track in arbitrary chunks must produce the same waveform as feeding it whole,
and filter state must survive chunk boundaries. They do NOT compare against the
existing full-file wavypy path -- output-equivalence with `get_waveform_cached`
is checked in the Task 2/3 integration tests.
"""
import numpy as np
import pytest

from backend.waveform_stream import (
    StreamingWaveformGenerator,
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
