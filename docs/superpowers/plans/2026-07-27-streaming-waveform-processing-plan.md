# Streaming Full-Track Waveform Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process complete tracks incrementally from ffmpeg PCM output, preserve waveform continuity across chunks, and reuse one temporary WAV for local key/BPM detection.

**Architecture:** Add a new streaming analyzer beside the existing full-file `backend/waveform.py` path. The analyzer owns ffmpeg, a WAV writer, a stateful wavypy-compatible generator, provisional snapshots, final normalization, and cleanup. The existing full-file path remains the fallback until output-equivalence tests pass.

**Tech Stack:** Python `asyncio`, `subprocess`, `wave`, NumPy, SciPy SOS filters, ffmpeg, wavypy internals, librosa.

## Global Constraints

- Do not modify the existing full-file waveform behavior until equivalence tests pass.
- Process signed 16-bit mono PCM at 44.1kHz, matching the current ffmpeg command.
- Preserve scipy filter state and incomplete pixel samples across chunks.
- Accumulate waveform points, not the full decoded audio array.
- Use the same temporary WAV for local key/BPM detection; never make a second full-track network request.
- Background analysis errors must not stop audio playback.

---

### Task 1: Extract a stateful streaming waveform generator

**Files:**
- Create: `backend/waveform_stream.py`
- Test: `backend/tests/test_waveform_stream.py`

**Interfaces:**
- `StreamingWaveformGenerator(sample_rate: int, channels: int, total_samples: int, width: int, bands: list[FrequencyBand])`.
- `feed(samples: np.ndarray) -> dict[str, list[float]]` returns only newly completed points.
- `finish() -> dict[str, list[float]]` flushes the final complete points and reports the final duration.
- `snapshot() -> dict` returns `{bands: {low, mid, high}, duration: float, complete: bool}`.

- [ ] **Step 1: Write the failing chunk-boundary tests**

```python
def test_chunked_output_matches_single_chunk_within_tolerance(fixture_samples):
    one = StreamingWaveformGenerator.from_samples(fixture_samples, width=600)
    chunked = StreamingWaveformGenerator.from_samples(fixture_samples, width=600, chunk_sizes=[137, 4096, 8191, 73])
    assert chunked.finish()['bands'].keys() == one.finish()['bands'].keys()
    for band in ('low', 'mid', 'high'):
        np.testing.assert_allclose(chunked.snapshot()['bands'][band], one.snapshot()['bands'][band], atol=2 / 32768)


def test_filter_state_survives_chunk_boundary(fixture_samples):
    generator = StreamingWaveformGenerator.from_samples(fixture_samples, width=600, chunk_sizes=[1, 1, 1, 4096])
    result = generator.finish()
    assert len(result['bands']['low']) > 0
    assert np.isfinite(result['bands']['mid']).all()
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `python3 -m pytest backend/tests/test_waveform_stream.py -q`

Expected: FAIL because `backend/waveform_stream.py` does not exist.

- [ ] **Step 3: Implement stateful filters and carry-over**

Create SOS filters once per band/profile/channel with `sosfilt_zi`. Store each returned `zf` and pass it into the next `sosfilt` call. Store a per-band remainder array; concatenate it with the next filtered chunk before grouping samples into `samples_per_pixel` windows. Emit min/max values with the stable signed-16-bit scale and do not normalize provisional points against a changing maximum.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m pytest backend/tests/test_waveform_stream.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/waveform_stream.py backend/tests/test_waveform_stream.py
git commit -m "feat: add stateful chunked waveform generator"
```

### Task 2: Add ffmpeg PCM streaming and one temporary WAV artifact

**Files:**
- Modify: `backend/waveform_stream.py`
- Test: `backend/tests/test_waveform_stream.py`

**Interfaces:**
- `async analyze_stream(stream_url: str, duration: float | None, width: int = 600, on_snapshot: Callable[[dict], Awaitable[None]] | None = None) -> dict`.
- The return value is `{bands: dict[str, list[float]], duration: float, temp_wav_path: str | None}`; callers own deletion of the temporary file after key analysis.

- [ ] **Step 1: Write the failing ffmpeg-reader test**

```python
@pytest.mark.asyncio
async def test_analyze_stream_writes_wav_and_emits_snapshots(monkeypatch, tmp_path):
    monkeypatch.setattr(waveform_stream, 'start_pcm_decoder', fake_pcm_decoder)
    snapshots = []
    result = await analyze_stream('https://example.test/track', 12.0, width=60, on_snapshot=snapshots.append)
    assert result['temp_wav_path'] is not None
    assert Path(result['temp_wav_path']).exists()
    assert snapshots[0]['complete'] is False
    assert snapshots[-1]['complete'] is True
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m pytest backend/tests/test_waveform_stream.py::test_analyze_stream_writes_wav_and_emits_snapshots -q`

Expected: FAIL because `analyze_stream` does not exist.

- [ ] **Step 3: Implement the decoder and WAV writer**

Launch ffmpeg with `-i <url> -ac 1 -ar 44100 -f s16le -acodec pcm_s16le -loglevel error pipe:1`. Read stdout in fixed byte blocks aligned to 2-byte samples. Write each decoded block into a `wave.Wave_write` temporary file configured as one channel, 2-byte samples, and 44100Hz. Feed NumPy `int16` arrays to `StreamingWaveformGenerator`, emit snapshots after each configured point interval, then close the WAV writer and mark the final snapshot complete. Use a 60-second subprocess timeout and terminate/clean up on cancellation.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m pytest backend/tests/test_waveform_stream.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/waveform_stream.py backend/tests/test_waveform_stream.py
git commit -m "feat: stream full-track PCM into waveform analysis"
```

### Task 3: Integrate streaming analysis with preview metadata jobs

**Files:**
- Modify: `backend/preview_jobs.py`
- Modify: `backend/main.py:264-365`
- Test: `backend/tests/test_preview_routes.py`

**Interfaces:**
- The preview analyzer calls `analyze_stream()` once, stores provisional snapshots, calls existing `detect_key()` with the resulting WAV only after FreqBlog misses, then publishes a terminal snapshot.
- `GET /preview/{track_id}/metadata` returns the latest `{status, revision, waveform, key, camelot, bpm}` snapshot.

- [ ] **Step 1: Write integration tests**

```python
@pytest.mark.asyncio
async def test_metadata_analysis_uses_one_stream(monkeypatch):
    calls = []
    async def fake_analyze(*args, **kwargs):
        calls.append(args[0])
        return {'bands': {'low': [0.1], 'mid': [0.2], 'high': [0.3]}, 'duration': 240.0, 'temp_wav_path': '/tmp/track.wav'}
    monkeypatch.setattr(main, 'analyze_stream', fake_analyze)
    await main.preview_job_manager.run_track_for_test(7)
    assert calls == ['https://example.test/track']
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest backend/tests/test_preview_routes.py::test_metadata_analysis_uses_one_stream -q`

Expected: FAIL because the metadata manager still calls `get_waveform_cached` and the old key path.

- [ ] **Step 3: Replace the analyzer callback**

Call `analyze_stream` once. Publish each callback snapshot with an incremented revision. Perform FreqBlog lookup before local analysis. On FreqBlog miss, call `_detect_key(temp_wav_path)` in `asyncio.to_thread`, save the result through the existing key cache, and publish key/BPM fields without blocking waveform snapshots. Delete the temporary WAV in a `finally` block after local analysis or FreqBlog completion.

- [ ] **Step 4: Preserve fallback behavior**

Leave `/preview/{track_id}` and `get_waveform_cached()` unchanged. If `analyze_stream` fails, publish `failed` metadata and let the instant stream continue. Do not change preview quality selection.

- [ ] **Step 5: Run backend tests**

Run: `python3 -m pytest backend/tests/ -q`

Expected: all existing tests pass except any previously known failures, plus the new preview tests pass. Record unrelated existing failures instead of changing them in this feature.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/preview_jobs.py backend/waveform_stream.py backend/tests/test_preview_routes.py backend/tests/test_waveform_stream.py
git commit -m "feat: integrate progressive full-track metadata analysis"
```

