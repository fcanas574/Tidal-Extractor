# Waveform Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start preview audio instantly via a fast stream endpoint, deliver the waveform progressively from a single ffmpeg download reused for key/BPM detection, and persist results per tidal track ID.

**Architecture:** Add `/preview/{id}/stream` and `/preview/{id}/metadata` beside the untouched combined endpoint, backed by the existing `PreviewJobManager`. A new pure stateful `StreamingWaveformGenerator` plus an ffmpeg-owning `analyze_stream()` replace full-file analysis behind output-equivalence tests. Results persist in a new `waveform_cache` SQLite table following the `key_cache` pattern.

**Tech Stack:** FastAPI, asyncio, subprocess ffmpeg (`s16le` pipe), NumPy, SciPy SOS filters, wavypy presets, aiosqlite-style `backend/models.py`, React 18, TypeScript, Vitest + Testing Library.

## Global Constraints

- Audio playback must never wait for analysis; `/stream` performs URL resolution only.
- The old combined `GET /preview/{track_id}` remains unchanged.
- Process signed 16-bit mono PCM at 44100 Hz; preserve scipy filter state and pixel remainders across chunks.
- Provisional waveform points use the stable scale `abs(max-min)/65536.0`; normalization happens only in `finish()`.
- One download feeds waveform AND key/BPM; never re-download for key detection in the new path.
- Temp WAV deleted in `finally`; background failures produce `failed` snapshots and never affect playback.
- Snapshot cadence: at most one provisional publication per second of audio (every `sample_rate` samples fed).
- Gates: `python3 -m pytest backend/tests/ -q` and `cd frontend && npm run build`.

---

### Task 1: Fast stream and metadata endpoints

**Files:**
- Modify: `backend/main.py` (preview section, after line ~290)
- Modify: `backend/preview_jobs.py` (analyzer call gains `track_id`)
- Create: `backend/tests/test_preview_routes.py`

**Interfaces:**
- Produces: `GET /preview/{track_id}/stream` → `{"track_id": int, "stream_url": str, "duration": float | None}`
- Produces: `GET /preview/{track_id}/metadata` → `{"track_id": int, "status": str, "revision": int, "waveform": dict | None, "key": str | None, "camelot": str | None, "bpm": float | None, "error": str | None}`
- Produces: `main.preview_job_manager: PreviewJobManager` whose analyzer signature becomes `(track_id: int, stream_url: str, duration: float | None) -> dict`
- Consumes: existing `PreviewJobManager.start_or_get/snapshot`, `get_waveform_cached`, `_detect_preview_key`

Note: this task wires the fast lifecycle with **today's full-file analysis** as the metadata worker; Task 6 swaps in streaming analysis.

- [ ] **Step 1: Write failing route tests**

```python
# backend/tests/test_preview_routes.py
import pytest
from fastapi.testclient import TestClient

import backend.main as main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main.auth_manager, "is_authenticated", True)
    return TestClient(main.app)


def _fake_track(monkeypatch, duration=240.0):
    class T:
        title = "t"; artist = type("A", (), {"name": "a"})()
        duration = duration
        def get_url(self): return "https://example.test/full-track"
    monkeypatch.setattr(main.auth_manager.session, "track", lambda _id: T())


def test_stream_route_returns_before_analyzer(client, monkeypatch):
    _fake_track(monkeypatch)
    monkeypatch.setattr(main, "get_waveform_cached",
                        lambda _: (_ for _ in ()).throw(AssertionError("must not run")))
    r = client.get("/preview/123/stream")
    assert r.status_code == 200
    body = r.json()
    assert body["stream_url"] == "https://example.test/full-track"
    assert body["duration"] == 240.0


def test_metadata_route_starts_job_and_returns_snapshot(client):
    import asyncio
    async def fake_analyzer(track_id, url, duration):
        await asyncio.sleep(0.01)
        return {}
    main.preview_job_manager.analyzer = fake_analyzer
    r = client.get("/preview/123/metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["track_id"] == 123
    assert body["status"] in {"queued", "processing", "complete"}
```

Note for implementer: if `auth_manager.session` is not a simple mockable object in tests, check how existing backend tests stub authentication (`ls backend/tests/`) and copy that pattern before running.

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `python3 -m pytest backend/tests/test_preview_routes.py -q`
Expected: FAIL with 404 for both routes.

- [ ] **Step 3: Implement `/stream`**

In `backend/main.py`, add below the existing preview endpoint:

```python
@app.get("/preview/{track_id}/stream")
async def preview_stream(track_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        track = auth_manager.session.track(track_id)
        orig_quality = auth_manager.session.config.quality
        auth_manager.session.config.quality = "LOW"
        try:
            url = track.get_url()
        finally:
            auth_manager.session.config.quality = orig_quality
        return {"track_id": track_id, "stream_url": url,
                "duration": getattr(track, "duration", None)}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Preview unavailable: {e}")
```

- [ ] **Step 4: Implement `/metadata` and the initial analyzer**

Extend the analyzer call site in `backend/preview_jobs.py` `_run_job` to
`self.analyzer(job.track_id, job.stream_url, job.duration)` (and update
existing lambdas in `test_preview_jobs.py` to accept three args). In `main.py`:

```python
import dataclasses
from backend.preview_jobs import PreviewJobManager

preview_job_manager = PreviewJobManager()

async def _legacy_analyzer(track_id: int, stream_url: str, duration):
    """Full-file analysis worker; replaced by streaming analysis in Task 6."""
    waveform = await asyncio.to_thread(get_waveform_cached, stream_url)
    key_data = await _detect_preview_key(stream_url, track_id)
    wf = waveform if waveform.get("bands") else None
    return {"waveform": wf, **key_data}

preview_job_manager.analyzer = _legacy_analyzer

@app.get("/preview/{track_id}/metadata")
async def preview_metadata(track_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        track = auth_manager.session.track(track_id)
        orig_quality = auth_manager.session.config.quality
        auth_manager.session.config.quality = "LOW"
        try:
            url = track.get_url()
        finally:
            auth_manager.session.config.quality = orig_quality
        snap = preview_job_manager.start_or_get(track_id, url, getattr(track, "duration", None))
        return dataclasses.asdict(snap)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Preview unavailable: {e}")
```

- [ ] **Step 5: Run focused tests**

Run: `python3 -m pytest backend/tests/test_preview_routes.py backend/tests/test_preview_jobs.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/preview_jobs.py backend/tests/test_preview_routes.py backend/tests/test_preview_jobs.py
git commit -m "feat: add instant preview stream and metadata routes"
```

### Task 2: Switch the player to the fast lifecycle

**Files:**
- Modify: `frontend/src/api.ts` (preview export, lines 212–214)
- Modify: `frontend/src/components/AudioPlayerFooter.tsx` (lines 231–259)
- Create: `frontend/src/components/AudioPlayerFooter.test.tsx`

**Interfaces:**
- Consumes: Task 1 endpoints.
- Produces: `preview.getStream(trackId: number): Promise<PreviewStream>` where `PreviewStream = { track_id: number; stream_url: string; duration: number | null }`; `preview.getMetadata(trackId: number): Promise<PreviewMetadata>` where `PreviewMetadata = { track_id: number; status: 'queued'|'processing'|'complete'|'failed'; revision: number; waveform: WaveformData | null; key: string | null; camelot: string | null; bpm: number | null; error: string | null }`.

- [ ] **Step 1: Write failing player tests**

```tsx
// frontend/src/components/AudioPlayerFooter.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import * as api from '../api';

vi.mock('../context/AppContext', () => ({
  useApp: () => ({
    state: { previewTrack: { id: 7, title: 'T', artist: 'A', cover_url: null }, previewPlaying: true },
    dispatch: vi.fn(),
  }),
}));
vi.mock('../api', async (orig) => ({
  ...(await orig()),
  preview: {
    getUrl: vi.fn(),
    getStream: vi.fn(),
    getMetadata: vi.fn(),
  },
}));

import AudioPlayerFooter from './AudioPlayerFooter';

describe('AudioPlayerFooter fast lifecycle', () => {
  it('starts audio from stream response before metadata resolves', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    let resolveMeta: (v: any) => void;
    (api.preview.getMetadata as any).mockImplementation(
      () => new Promise((res) => { resolveMeta = res; }));
    render(<AudioPlayerFooter />);
    // Audio element constructed from the stream response while metadata still pending
    await waitFor(() =>
      expect(document.querySelector('audio') ?? (window.HTMLMediaElement.prototype.src ? true : null)).toBeTruthy());
    expect(api.preview.getMetadata).toHaveBeenCalledWith(7);
    expect(resolveMeta!).toBeDefined();
    expect(play).toHaveBeenCalled();
  });

  it('applies only metadata matching the active preview token', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    // First getMetadata resolves for an OLD track id (9) after the active one is 7;
    // component must not apply it because snapshot track_id mismatches active preview.
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 9, status: 'complete', revision: 2,
      waveform: { bands: { low: [0.9], mid: [0.9], high: [0.9] }, colors: {}, duration: 999 },
      key: null, camelot: null, bpm: null, error: null,
    });
    const { container } = render(<AudioPlayerFooter />);
    await waitFor(() => expect(play).toHaveBeenCalled());
    // Give any erroneous application a tick, then assert no waveform was drawn from track 9's data
    await new Promise((r) => setTimeout(r, 800));
    expect(container.querySelector('canvas')).toBeNull(); // shimmer placeholder still shown
  });
});
```

- [ ] **Step 2: Run focused test to verify it fails**

Run: `cd frontend && npx vitest run src/components/AudioPlayerFooter.test.tsx`
Expected: FAIL — `preview.getStream` is undefined.

- [ ] **Step 3: Add typed API methods**

Keep the existing `getUrl` line byte-for-byte and append inside the `preview` object in `frontend/src/api.ts`, plus the interfaces above `WaveformData`'s consumers:

```ts
export interface PreviewStream { track_id: number; stream_url: string; duration: number | null; }
export interface PreviewMetadata {
  track_id: number;
  status: 'queued' | 'processing' | 'complete' | 'failed';
  revision: number;
  waveform: WaveformData | null;
  key: string | null; camelot: string | null; bpm: number | null; error: string | null;
}

export const preview = {
  getUrl: (trackId: number) => request<{ stream_url: string; waveform: WaveformData | null; key: string | null; camelot: string | null; bpm: number | null }>(`/preview/${trackId}`),
  getStream: (trackId: number) => request<PreviewStream>(`/preview/${trackId}/stream`),
  getMetadata: (trackId: number) => request<PreviewMetadata>(`/preview/${trackId}/metadata`),
};
```

- [ ] **Step 4: Start audio immediately, poll metadata with stale protection**

Rewrite the load effect in `AudioPlayerFooter.tsx` (replacing lines 231–259):

```tsx
const previewTokenRef = useRef(0);

useEffect(() => {
  if (!previewTrack) return;
  const trackId = previewTrack.id;
  const token = ++previewTokenRef.current;
  let cancelled = false;
  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  setCurrentTime(0); setDuration(0); setWaveform(null);
  setKeyCamelot(null); setBpm(null);

  const active = () => !cancelled && token === previewTokenRef.current;

  const poll = () => {
    pollTimer = setTimeout(async () => {
      if (!active()) return;
      try {
        const meta = await preview.getMetadata(trackId);
        if (!active()) return;
        if (meta.track_id === trackId) {
          if (meta.waveform?.bands) setWaveform(meta.waveform);
          if (meta.camelot) setKeyCamelot(meta.camelot);
          if (meta.bpm) setBpm(meta.bpm);
          if (meta.status === 'complete' || meta.status === 'failed') return; // terminal: stop polling
        }
        poll();
      } catch { /* non-blocking: keep placeholder */ }
    }, 750);
  };

  preview.getStream(trackId).then((r) => {
    if (!active()) return;
    const audio = new Audio(r.stream_url);
    audioRef.current = audio;
    audio.addEventListener('timeupdate', () => setCurrentTime(audio.currentTime));
    audio.addEventListener('loadedmetadata', () => setDuration(audio.duration));
    audio.addEventListener('ended', () => dispatch({ type: 'CLEAR_PREVIEW' }));
    audio.addEventListener('error', () => dispatch({ type: 'CLEAR_PREVIEW' }));
    audio.play().catch(() => dispatch({ type: 'CLEAR_PREVIEW' }));
    poll();
  }).catch(() => dispatch({ type: 'CLEAR_PREVIEW' }));

  return () => {
    cancelled = true;
    if (pollTimer) clearTimeout(pollTimer);
    audioRef.current?.pause();
    audioRef.current = null;
  };
}, [previewTrack?.id]);
```

While `waveform === null`, render a shimmer placeholder instead of the canvas:

```tsx
{waveform ? (
  <canvas ref={canvasRef} onClick={seek} /* existing handlers/props unchanged */ />
) : (
  <div className="w-full mb-2 rounded animate-pulse"
       style={{ height: '56px', background: 'var(--bg-surface)', opacity: 0.4 }} />
)}
```

Also gate the draw effect on `waveform?.bands` (it already returns early when absent).

- [ ] **Step 5: Run frontend tests and build**

Run: `cd frontend && npx vitest run src/components/AudioPlayerFooter.test.tsx && npm run build`
Expected: PASS, clean Vite build.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/AudioPlayerFooter.tsx frontend/src/components/AudioPlayerFooter.test.tsx
git commit -m "feat: start preview audio before metadata analysis"
```

### Task 3: Stateful streaming waveform generator

**Files:**
- Create: `backend/waveform_stream.py` (generator part only)
- Test: `backend/tests/test_waveform_stream.py`

**Interfaces:**
- Produces: `StreamingWaveformGenerator(sample_rate: int, total_samples: int, width: int = 600, preset: str = "club")` with:
  - `feed(samples: np.ndarray) -> dict[str, list[float]]` — int16 mono samples in; newly completed per-pixel amplitudes out (`abs(max-min)/65536.0`, unnormalized), keyed by band name.
  - `finish() -> dict` — `{"bands": {name: [float]}, "duration": float, "complete": True}` with per-band max-normalization applied.
  - `snapshot(complete: bool = False) -> dict` — accumulated points in current state, same shape with `"complete": False`.
- Consumes: `wavy.get_band_preset(name)` returning `[FrequencyBand]` (each with `.name`, `.filter_profiles`; profiles have `.cutoff_freq`, `.filter_type`, `.order`) and `FilterType` from `backend/wavypy/wavy.py`, mirroring `BandSplitter._create_filter` (`butter(order, cutoff/nyquist, btype=..., output='sos')` + `sosfilt_zi`).

- [ ] **Step 1: Write failing chunk-boundary tests**

```python
# backend/tests/test_waveform_stream.py
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
```

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `python3 -m pytest backend/tests/test_waveform_stream.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the generator**

```python
# backend/waveform_stream.py
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
```

Implementer note: `finish()` normalizes each band by its own max, matching the existing conversion in `backend/waveform.py:166-177`. If a chunk-boundary test fails only on the last partial pixel, adjust the `samples_per_pixel // 2` flush threshold — but do not rescale already-emitted provisional points.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m pytest backend/tests/test_waveform_stream.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/waveform_stream.py backend/tests/test_waveform_stream.py
git commit -m "feat: add stateful chunked waveform generator"
```

### Task 4: ffmpeg PCM streaming with one temp WAV

**Files:**
- Modify: `backend/waveform_stream.py` (append reader)
- Test: `backend/tests/test_waveform_stream.py` (append)

**Interfaces:**
- Produces: `start_pcm_decoder(stream_url: str) -> asyncio.subprocess.Process` launching
  `ffmpeg -i <url> -ac 1 -ar 44100 -f s16le -acodec pcm_s16le -loglevel error pipe:1`.
- Produces: `async analyze_stream(stream_url: str, duration: float | None, width: int = 600, on_snapshot: Callable[[dict], Awaitable[None]] | None = None, temp_dir: str | None = None, sample_rate: int = 44100) -> dict` returning `{"bands": dict[str, list[float]], "duration": float, "temp_wav_path": str}` (final snapshot also carries `"complete": True`). Callers delete `temp_wav_path`.
- Consumes: `StreamingWaveformGenerator` from Task 3.

- [ ] **Step 1: Write failing reader tests**

```python
# appended to backend/tests/test_waveform_stream.py
import io
import wave as wavemod
import pytest
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
```

Add `from pathlib import Path` to the imports at the top of the test file.

- [ ] **Step 2: Run focused test to verify it fails**

Run: `python3 -m pytest backend/tests/test_waveform_stream.py -q -k analyze_stream`
Expected: FAIL — `start_pcm_decoder`/`analyze_stream` missing.

- [ ] **Step 3: Implement decoder + reader + WAV writer**

Append to `backend/waveform_stream.py`:

```python
import asyncio
import contextlib
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


async def analyze_stream(stream_url, duration, width=600, on_snapshot=None,
                         temp_dir=None, sample_rate=44100):
    fd, wav_path = tempfile.mkstemp(suffix=".wav", dir=temp_dir)
    os.close(fd)
    proc = await start_pcm_decoder(stream_url)
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
                    block = await asyncio.wait_for(proc.stdout.read(READ_BYTES),
                                                   timeout=READ_TIMEOUT_S)
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
                    await on_snapshot(gen.snapshot(complete=False))
        rc = await proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg exited {rc}")
        final = gen.finish()
        final["duration"] = consumed / sample_rate
        final["temp_wav_path"] = wav_path
        if on_snapshot:
            await on_snapshot(final)
        return final
    except BaseException:
        proc.kill()
        with contextlib.suppress(ProcessLookupError):
            await proc.wait()
        with contextlib.suppress(OSError):
            os.unlink(wav_path)
        raise
```

Note: `gen.finish()` sets `"complete": True` already, so the final `on_snapshot` call receives the terminal snapshot.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m pytest backend/tests/test_waveform_stream.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/waveform_stream.py backend/tests/test_waveform_stream.py
git commit -m "feat: stream full-track PCM into waveform analysis"
```

### Task 5: Persist waveforms per tidal track ID

**Files:**
- Modify: `backend/models.py` (DDL block near line 55; methods near line 189)
- Create: `backend/tests/test_waveform_cache.py`

**Interfaces:**
- Consumes: the `Database` class patterns `get_key_cache`/`set_key_cache` (`backend/models.py:189-207`) and however existing DB tests construct `Database` (check `backend/tests/` first).
- Produces: `await db.get_waveform_cache(tidal_id: str) -> dict | None` returning `{"bands": dict, "duration": float}` (JSON-decoded) or `None`.
- Produces: `await db.set_waveform_cache(tidal_id: str, bands: dict, duration: float) -> None`.

- [ ] **Step 1: Write failing cache tests**

```python
# backend/tests/test_waveform_cache.py
import pytest
from backend.models import Database


@pytest.mark.asyncio
async def test_roundtrip(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.init()
    assert await db.get_waveform_cache("123") is None
    await db.set_waveform_cache("123", {"low": [0.1], "mid": [0.2], "high": [0.3]}, 210.5)
    got = await db.get_waveform_cache("123")
    assert got == {"bands": {"low": [0.1], "mid": [0.2], "high": [0.3]}, "duration": 210.5}
    await db.close()
```

Adjust the constructor/init calls to match how existing backend tests build `Database` (open `backend/tests/` and copy their setup before running).

- [ ] **Step 2: Run focused test to verify it fails**

Run: `python3 -m pytest backend/tests/test_waveform_cache.py -q`
Expected: FAIL — methods missing.

- [ ] **Step 3: Implement table and methods**

Add to the DDL block in `_init_tables`:

```sql
CREATE TABLE IF NOT EXISTS waveform_cache (
    tidal_id TEXT PRIMARY KEY,
    bands_json TEXT NOT NULL,
    duration REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Add methods mirroring `key_cache`:

```python
async def get_waveform_cache(self, tidal_id: str):
    rows = await self._conn.execute_fetchall(
        "SELECT bands_json, duration FROM waveform_cache WHERE tidal_id = ?", (tidal_id,))
    if not rows:
        return None
    import json
    return {"bands": json.loads(rows[0]["bands_json"]), "duration": rows[0]["duration"]}

async def set_waveform_cache(self, tidal_id: str, bands: dict, duration: float):
    import json
    await self._conn.execute(
        """INSERT INTO waveform_cache (tidal_id, bands_json, duration)
           VALUES (?, ?, ?)
           ON CONFLICT(tidal_id) DO UPDATE SET
               bands_json = excluded.bands_json,
               duration = excluded.duration,
               created_at = CURRENT_TIMESTAMP""",
        (tidal_id, json.dumps(bands), duration),
    )
    await self._conn.commit()
```

(Move both `import json` statements to the module top to match file style.)

- [ ] **Step 4: Run focused tests**

Run: `python3 -m pytest backend/tests/test_waveform_cache.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/tests/test_waveform_cache.py
git commit -m "feat: persist waveform cache keyed by tidal track ID"
```

### Task 6: Wire streaming analysis into the metadata job

**Files:**
- Modify: `backend/main.py` (replace `_legacy_analyzer` from Task 1)
- Modify: `backend/preview_jobs.py` (add `publish_progress`)
- Create: `backend/tests/test_preview_analysis.py`

**Interfaces:**
- Consumes: `analyze_stream` (Task 4), `db.get_waveform_cache`/`set_waveform_cache` (Task 5), `lookup_track_metadata` from `backend.freqblog`, `detect_key` from `backend.key_detection`, `preview_job_manager` (Task 1).
- Produces: `main.preview_analyzer(track_id: int, stream_url: str, duration: float | None) -> dict` publishing provisional snapshots via `preview_job_manager.publish_progress(track_id, updates)` where `updates ⊆ {waveform, key, camelot, bpm}`.
- Produces: `PreviewJobManager.publish_progress(self, track_id: int, updates: dict) -> None` merging fields onto the live snapshot with a revision bump under the existing lock.
- The analyzer's returned dict contains final `{"waveform": {...}, "key": ..., "camelot": ..., "bpm": ...}`.

- [ ] **Step 1: Write failing integration tests**

```python
# backend/tests/test_preview_analysis.py
import pytest
import backend.main as main


@pytest.mark.asyncio
async def test_uses_one_stream_and_persists(monkeypatch):
    calls = []

    async def fake_analyze(url, duration, **kw):
        calls.append(url)
        return {"bands": {"low": [0.1], "mid": [0.2], "high": [0.3]},
                "duration": 240.0, "temp_wav_path": None}

    async def none(_):
        return None

    saved = {}

    async def fake_set(tid, bands, duration):
        saved[tid] = bands

    async def fake_fb(*a, **k):
        return None

    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main.db, "get_waveform_cache", none)
    monkeypatch.setattr(main.db, "set_waveform_cache", fake_set)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    monkeypatch.setattr(main.auth_manager.session, "track",
                        lambda _id: type("T", (), {"title": "t", "artist": type("A", (), {"name": "a"})()})())

    result = await main.preview_analyzer(7, "https://s/7", 240.0)
    assert calls == ["https://s/7"]                    # exactly one download
    assert saved["7"]["low"] == [0.1]                  # persisted by tidal id
    assert result["waveform"]["bands"]["mid"] == [0.2]


@pytest.mark.asyncio
async def test_cache_hit_skips_download(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("must not download")

    async def hit(_):
        return {"bands": {"low": [1.0], "mid": [1.0], "high": [1.0]}, "duration": 12.0}

    monkeypatch.setattr(main, "analyze_stream", boom)
    monkeypatch.setattr(main.db, "get_waveform_cache", hit)
    result = await main.preview_analyzer(9, "https://s/9", 12.0)
    assert result["waveform"]["bands"]["high"] == [1.0]


@pytest.mark.asyncio
async def test_local_key_detection_reads_temp_wav_not_network(monkeypatch):
    seen, deleted = {}, []
    calls = []

    async def fake_analyze(url, duration, **kw):
        return {"bands": {"low": [0.5], "mid": [0.5], "high": [0.5]},
                "duration": 10.0, "temp_wav_path": "/tmp/fake.wav"}

    async def fake_detect(path):
        seen["path"] = path
        return {"key": "Am", "camelot": "4A", "bpm": 128.0, "confidence": 0.9}

    async def fake_fb(*a, **k):
        return None

    async def fake_set_key(*a, **k):
        pass

    async def none(_):
        return None

    monkeypatch.setattr(main, "analyze_stream", fake_analyze)
    monkeypatch.setattr(main, "_detect_key_local", fake_detect)
    monkeypatch.setattr(main, "_freqblog_lookup", fake_fb)
    monkeypatch.setattr(main.db, "get_waveform_cache", none)
    monkeypatch.setattr(main.db, "set_key_cache", fake_set_key)
    async def fake_remove(path):
        deleted.append(path)
    monkeypatch.setattr(main, "_remove_temp_file", fake_remove)
    monkeypatch.setattr(main.auth_manager.session, "track",
                        lambda _id: type("T", (), {"title": "t", "artist": type("A", (), {"name": "a"})()})())

    result = await main.preview_analyzer(11, "https://s/11", 10.0)
    assert seen["path"] == "/tmp/fake.wav"
    assert deleted == ["/tmp/fake.wav"]
    assert result["camelot"] == "4A"


@pytest.mark.asyncio
async def test_analysis_failure_raises_into_failed_snapshot(monkeypatch):
    async def fail(*a, **k):
        raise RuntimeError("decode died")

    async def none(_):
        return None

    monkeypatch.setattr(main, "analyze_stream", fail)
    monkeypatch.setattr(main.db, "get_waveform_cache", none)
    monkeypatch.setattr(main.auth_manager.session, "track",
                        lambda _id: type("T", (), {"title": "t", "artist": type("A", (), {"name": "a"})()})())
    with pytest.raises(RuntimeError):  # manager converts raised errors into failed snapshots
        await main.preview_analyzer(13, "https://s/13", 5.0)
```

Remove the unused `calls = []` in the third test if linting complains.

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `python3 -m pytest backend/tests/test_preview_analysis.py -q`
Expected: FAIL — `preview_analyzer`, `_freqblog_lookup`, `_detect_key_local`, `publish_progress` missing.

- [ ] **Step 3: Implement the analyzer, helpers, and publish_progress**

In `backend/main.py`, replace `_legacy_analyzer` (keep `_WAVEFORM_COLORS` at module level):

```python
_WAVEFORM_COLORS = {"low": "#0055e2", "mid": "#f2aa3c", "high": "#ffffff"}


async def _freqblog_lookup(title: str, artist: str):
    from backend.freqblog import lookup_track_metadata
    return await lookup_track_metadata(title, artist)


async def _detect_key_local(path: str):
    from backend.key_detection import detect_key
    return await asyncio.to_thread(detect_key, path)


async def _detect_preview_key_cached(track_id: int) -> dict:
    cached = await db.get_key_cache(f"preview_key_{track_id}")
    if not cached:
        return {}
    return {"key": cached.get("key"), "camelot": cached.get("camelot"),
            "bpm": cached.get("bpm")}


def _remove_temp_file(path: str | None) -> None:
    if path and os.path.exists(path):
        os.unlink(path)


async def preview_analyzer(track_id: int, stream_url: str, duration: float | None) -> dict:
    cached = await db.get_waveform_cache(str(track_id))
    if cached:
        key_data = await _detect_preview_key_cached(track_id)
        return {"waveform": {"bands": cached["bands"], "colors": _WAVEFORM_COLORS,
                             "duration": cached["duration"]}, **key_data}

    track = auth_manager.session.track(track_id)
    title = getattr(track, "title", "") or ""
    artist = getattr(getattr(track, "artist", None), "name", "") or ""

    async def on_snap(snap):
        preview_job_manager.publish_progress(track_id, {"waveform": snap})

    result = await analyze_stream(stream_url, duration, on_snapshot=on_snap)
    waveform = {"bands": result["bands"], "colors": _WAVEFORM_COLORS,
                "duration": result["duration"]}
    preview_job_manager.publish_progress(track_id, {"waveform": waveform})

    key_payload = {}
    tmp_path = result.get("temp_wav_path")
    try:
        metadata = await _freqblog_lookup(title, artist)
        if metadata:
            key_payload = {"key": metadata["key"], "camelot": metadata["camelot"],
                           "bpm": metadata.get("bpm")}
        elif tmp_path:
            local = await _detect_key_local(tmp_path)
            key_payload = {"key": local.get("key"), "camelot": local.get("camelot"),
                           "bpm": local.get("bpm")}
        if key_payload.get("key"):
            await db.set_key_cache(f"preview_key_{track_id}", key_payload["key"],
                                   key_payload.get("camelot"), 1.0,
                                   bpm=key_payload.get("bpm"))
    except Exception as e:
        logger.warning("key detection failed for %s: %s", track_id, e)
    finally:
        await db.set_waveform_cache(str(track_id), result["bands"], result["duration"])
        _remove_temp_file(tmp_path)
    return {"waveform": waveform, **key_payload}


preview_job_manager.analyzer = preview_analyzer
```

Add to `backend/preview_jobs.py`:

```python
def publish_progress(self, track_id: int, updates: dict) -> None:
    """Merge partial fields into the live snapshot with a revision bump."""
    with self._lock:
        job = self._jobs.get(track_id)
        if job is None:
            return
        merged = {
            "status": "processing",
            **{k: updates[k] for k in ("waveform", "key", "camelot", "bpm") if k in updates},
        }
        self._update_snapshot_locked(job, **merged)
```

Verify `_run_job` still converts analyzer exceptions into `failed` snapshots (existing behavior — do not regress it).

- [ ] **Step 4: Run backend suite**

Run: `python3 -m pytest backend/tests/ -q`
Expected: all pass; record (do not fix) unrelated pre-existing failures.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/preview_jobs.py backend/tests/test_preview_analysis.py
git commit -m "feat: integrate progressive full-track metadata analysis"
```

### Task 7: Full verification gates

**Files:** none created; verification only.

- [ ] **Step 1: Backend gate**

Run: `python3 -m pytest backend/tests/ -q`
Expected: PASS (or documented pre-existing failures only).

- [ ] **Step 1b: Streaming-vs-full-file equivalence fixture**

This is the spec's equivalence gate: `analyze_stream` output must match today's
`build_waveform()` within tolerance for the same audio. Append to
`backend/tests/test_waveform_stream.py`:

```python
@pytest.mark.asyncio
async def test_analyze_stream_matches_full_file_build_waveform(tmp_path):
    """Spec equivalence gate vs the legacy backend.waveform.build_waveform path."""
    from backend.waveform import build_waveform

    # Deterministic 8s stereo-ish test tone written as a real WAV file
    import wave as wavemod
    rng = np.random.default_rng(7)
    sr = 44100
    t = np.arange(sr * 8)
    sig = (9000 * np.sin(2 * np.pi * 180 * t / sr)
           + 5000 * np.sin(2 * np.pi * 2500 * t / sr)
           + rng.integers(-500, 500, t.size)).astype(np.int16)
    wav_file = tmp_path / "fixture.wav"
    with wavemod.open(wav_file, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(sig.tobytes())

    streaming = await waveform_stream.analyze_stream(str(wav_file), 8.0, width=600,
                                                     temp_dir=str(tmp_path))
    legacy = build_waveform(str(wav_file))
    assert legacy.get("bands"), "legacy path returned empty"
    for band in ("low", "mid", "high"):
        a = np.array(streaming["bands"][band])
        b = np.array(legacy["bands"][band])
        assert len(a) > 0 and len(b) > 0
        n = min(len(a), len(b))
        np.testing.assert_allclose(a[:n], b[:n], atol=0.02)

    import os as _os
    _os.unlink(streaming["temp_wav_path"])
```

If this fails on filter shape but passes on point count, compare against what
`build_waveform` produces after its own normalization and align lengths before
asserting; do not weaken below `atol=0.02`. If the two paths disagree beyond
tolerance, fix `StreamingWaveformGenerator`'s filter construction to match
`BandSplitter._create_filter`, not the test.

- [ ] **Step 2: Frontend gate**

Run: `cd frontend && npm run build`
Expected: clean build.

- [ ] **Step 3: Manual checklist**

Start the app, then verify with a multi-minute track:
1. Click preview → audio starts immediately, shimmer placeholder shows, waveform fills in progressively.
2. Seek during analysis → playback seeks correctly; the final normalized waveform replaces provisional without a visual jump.
3. Close and re-preview the SAME track → full waveform appears instantly (cache hit; backend logs show no ffmpeg spawn).
4. Old endpoint sanity: `curl localhost:<port>/api/preview/<id> | head -c 200` still returns the combined payload.

Record results in handoff notes. No commit unless docs change.
