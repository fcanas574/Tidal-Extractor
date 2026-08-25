# Waveform Streaming and Instant Track Playback

## Goal

Make previewing a track start playback immediately, deliver the waveform progressively from a single download, reuse that download for key/BPM detection, and persist analysis results per track so repeat previews are instant. This completes roadmap items 1 and 2 of the 2026-07-27 progressive preview design; color modes remain out of scope.

## Context

Today `GET /preview/{track_id}` blocks playback until ffmpeg downloads the full stream, wavypy builds the complete multiband waveform, and key/BPM detection runs — including a second full download of the track inside `_detect_preview_key`. `PreviewJobManager` (`backend/preview_jobs.py`) already implements the metadata job lifecycle with tests, but neither `/stream` nor `/metadata` endpoints exist and the frontend still calls the blocking endpoint.

## Architecture

```text
Preview click
  ├─ GET /preview/{id}/stream        → {track_id, stream_url, duration}
  ├─ browser constructs new Audio(stream_url) → playback starts
  ├─ GET /preview/{id}/metadata      → starts-or-attaches per-track job, returns snapshot
  │     └─ background job:
  │          1. SQLite cache hit by tidal_id? → publish complete waveform instantly
  │          2. ffmpeg pipes URL → s16le PCM on stdout (single download)
  │          3. PCM chunks → StreamingWaveformGenerator (provisional snapshots)
  │          4. same chunks → temp WAV file
  │          5. finish() → final normalized waveform → persist to SQLite cache
  │          6. key/BPM: FreqBlog first; on miss, detect_key(temp WAV) — no second download
  │          7. delete temp WAV; publish terminal snapshot
  └─ frontend polls /metadata every ~750ms until status ∈ {complete, failed}
```

Properties:

- Audio never waits for analysis. The stream endpoint only resolves the low-quality URL using the existing quality selection.
- One download total for waveform + key/BPM, eliminating the double download in `_detect_preview_key`.
- The old combined `GET /preview/{track_id}` remains unchanged as fallback.
- Polling instead of WebSocket keeps the preview path independent of the download WS.
- Stale-result protection: the frontend holds a monotonic preview token; snapshots apply only when token and track_id match the active preview.

Execution is incremental: first wire the fast endpoints with today's full-file analyzer as the metadata worker (playback becomes instantly faster), then introduce streaming analysis behind output-equivalence tests, then add persistence.

## Backend components

### GET /preview/{track_id}/stream

Auth check → temporarily set quality LOW as today → `track.get_url()` → return `{track_id, stream_url, duration}`. No analysis calls.

### StreamingWaveformGenerator (new backend/waveform_stream.py)

Pure-Python stateful class, no I/O:

- Constructed with `sample_rate`, `total_samples` (Tidal duration × 44100), `width=600`, club-preset band filters matching wavypy.
- `feed(samples) -> dict`: per-band scipy SOS filtering with `zi` carry-over across chunks, concatenation with the previous remainder, min/max points per pixel on the stable signed-16-bit scale; returns only newly completed points.
- `finish() -> dict`: flushes remainders and applies final per-band normalization. Normalization happens only here, so provisional renders never jump.
- Provisional snapshots use the raw s16 scale; the frontend redraws whatever snapshot arrives.

### analyze_stream(stream_url, duration, width=600, on_snapshot=None)

Owns the ffmpeg subprocess (`-ac 1 -ar 44100 -f s16le pipe:1`), reads byte blocks aligned to 2-byte samples, feeds the generator, writes every block to one temp WAV via `wave.Wave_write`, emits provisional snapshots at most once per second of audio (every `sample_rate` samples fed), coalesced so slow consumers never queue multiple pending snapshots. Returns `{bands, duration, temp_wav_path}`; callers own temp-file deletion after key analysis. 60-second subprocess timeout; terminate and clean up on cancellation.

### Analyzer integration

`PreviewJobManager` is unchanged. Its analyzer callback becomes: DB cache check → hit: publish complete immediately; miss: `analyze_stream`, publishing each provisional snapshot with an incremented revision, then FreqBlog lookup → on miss, local `detect_key(temp_wav_path)` via `asyncio.to_thread`, saved through the existing key cache → persist final result → delete temp WAV in `finally`.

Equivalence gate: before streaming replaces it, chunked output must match today's full-file `build_waveform()` within tolerance on a deterministic fixture. Until then the old analyzer serves as the metadata worker.

## Persistence

New table `waveform_cache(tidal_id TEXT PRIMARY KEY, bands_json TEXT, duration REAL, created_at)` with `get_waveform_cache`/`set_waveform_cache` following the existing `key_cache` pattern in `backend/db.py`. Keyed by tidal track ID — stable across rotating signed URLs and restarts. Key/BPM already persists via `key_cache`. The URL-keyed LRU leaves the preview path; the legacy endpoint retains it.

## Frontend

- `api.ts`: add `preview.getStream(id)` and `preview.getMetadata(id)`; keep `getUrl()` for fallback.
- On preview select: reset state → `getStream` → construct `Audio` and start playback → poll metadata every 750ms with an incrementing local token; apply snapshots only when token + track_id match. AbortControllers cancel both requests on change/close.
- No waveform yet: canvas shows a subtle "analyzing…" placeholder shimmer.
- Metadata failure: non-blocking "waveform unavailable" state; polling stops; audio continues.

## Error handling

- Stream failure clears the active preview using the existing toast pattern.
- Analysis failure publishes a `failed` snapshot; audio plays on. No automatic retry; a re-click re-triggers the job.
- ffmpeg death mid-stream marks the job failed; the temp WAV is deleted in `finally`.

## Testing

- Chunked generator vs single-shot equivalence within `atol = 2/32768`; filter continuity at pathological boundaries (1-sample chunks); finite outputs.
- `analyze_stream` against a fake PCM decoder: temp WAV written, snapshots end complete, cancellation cleans up.
- Route tests: `/stream` never invokes the analyzer; `/metadata` returns queued/processing snapshots; analyzer errors become `failed` snapshots without affecting the stream route.
- Frontend tests: audio starts before metadata resolves; stale metadata cannot replace the active track's waveform.
- Manual: multi-minute track — audio starts first, waveform fills in, seek during analysis works, normalized final waveform replaces provisional; second play of the same track shows the waveform instantly from cache.
- Gates: `python3 -m pytest backend/tests/ -q` and `cd frontend && npm run build`.

## Non-goals

- 3Band/RGB color mode setting (separate roadmap item).
- Backend proxy/tee for single-download browser audio (deferred with the July design).
- Changing preview quality selection or the quality fallback ladder.
- Rewriting wavypy or retry logic for failed analyses.
