# Progressive Full-Track Previews and Waveform Color Modes

## Goal

Make full-track previews start playing immediately while waveform, key, and BPM metadata are generated progressively in the background; add selectable 3Band and RGB waveform color modes; preserve the current preview endpoint as a fallback; and defer download-speed changes to a separate quality-preserving research plan.

## Context

The current preview flow in `backend/main.py` obtains a low-quality stream URL, synchronously waits for `get_waveform_cached()`, then performs key/BPM detection before returning `stream_url` to `AudioPlayerFooter.tsx`. Waveform generation in `backend/waveform.py` invokes wavypy after ffmpeg has decoded the complete stream into a temporary WAV. Wavypy then loads the complete file into a NumPy array.

The current wavypy output already contains independent low, mid, and high bands. The frontend canvas already renders those bands separately, but its colors are hardcoded to the 3Band palette.

Rekordbox documents BLUE, RGB, and 3Band waveform modes. This project will initially expose the requested 3Band and RGB modes only:

- 3Band: low = blue, mid = orange, high = white.
- RGB: low = red, mid = green, high = blue.

References: [rekordbox 7 manual](https://cdn.rekordbox.com/files/20260409151936/rekordbox7.214_manual_EN.pdf), [rekordbox waveform color reference](https://www.deejayplaza.com/en/articles/color-waveform-rekordbox).

## Architecture

The implementation uses an additive fast path rather than changing the existing endpoint in place:

```text
Preview click
  ├─ GET /preview/{track_id}/stream
  │    └─ return stream_url immediately
  ├─ browser starts full-track audio playback
  └─ GET /preview/{track_id}/metadata
       └─ background/incremental waveform + key/BPM result
```

The existing `GET /preview/{track_id}` endpoint remains available as a compatibility fallback during rollout. The frontend will opt into the fast path through a narrowly scoped preview API implementation, with clear cancellation and stale-track protection.

The fast path will use polling rather than the global download WebSocket. `GET /preview/{track_id}/stream` returns `{track_id, stream_url, duration}`. The first `GET /preview/{track_id}/metadata` starts or finds a per-track analysis job and returns `{track_id, status, revision, waveform, key, camelot, bpm}`. Subsequent requests return the newest snapshot until `status` is `complete` or `failed`. The frontend polls only while that track is active and stops polling on cancellation or terminal status.

The first implementation may use two Tidal reads: the browser’s direct stream and the backend’s background analysis stream. A single-download backend media proxy/tee is explicitly out of scope for this phase because it introduces HTTP range, seeking, content-type, and signed-URL forwarding risks.

## Incremental waveform processing

Add a streaming analysis boundary without changing wavypy’s existing full-file API. The streaming path will:

1. Resolve the full-track preview URL at click time.
2. Start an ffmpeg subprocess that decodes the URL to signed 16-bit PCM on stdout.
3. Read fixed-size PCM chunks from stdout.
4. Feed chunks into a stateful waveform generator.
5. Preserve scipy SOS filter state between chunks for every band/filter/channel.
6. Preserve incomplete samples at chunk boundaries until enough samples form the next waveform point.
7. Write the same decoded PCM chunks into one temporary WAV file while accumulating only the configured waveform points, not a second in-memory copy of the decoded audio.
8. Return provisional waveform data as metadata becomes available and a final normalized waveform when processing completes.

The streaming generator must receive the expected total sample count or duration before processing so `samples_per_pixel` remains stable for the complete track. Prefer the Tidal track duration already available from the track object; validate the resulting duration against decoded sample count and fall back to a fixed pixels-per-second scale if duration is unavailable.

Progressive normalization must not make already-rendered sections jump unpredictably. The initial implementation should use a stable signed-16-bit scale for provisional points and apply final per-band normalization only in the completed result. The frontend should accept replacement metadata for the same track and redraw the complete waveform.

The existing `backend/waveform.py` and wavypy full-file path remain unchanged until the streaming implementation has output-equivalence tests. If the streaming path fails, the metadata request returns a structured failure and the audio continues playing.

## Metadata lifecycle

The stream response contains only the resolved URL and track identity. The metadata response is independently cancellable and must include a track ID/version so late results cannot overwrite a newer preview.

The metadata job must reuse the temporary WAV produced during streaming for local key/BPM detection; it must not make a second full-track network request. FreqBlog lookup remains the first key/BPM tier. If FreqBlog misses, local detection may continue in the background and must never delay playback. The temporary WAV is deleted after local analysis and is also deleted on cancellation or failure.

Waveform and key/BPM results should use the existing database cache where possible. Cache identity should be stable for the track and analysis mode, not solely the rotating signed stream URL. Cache entries must distinguish waveform mode only at presentation time because both color modes use the same low/mid/high numeric bands.

## Frontend color preferences

Extend the existing settings model with a persisted `waveform_color` value constrained to `3band | rgb`, defaulting to `3band` to preserve current appearance.

Add a Waveform section to `frontend/src/components/SettingsPanel.tsx`. Changing the selection should update the local settings state immediately and persist through the existing settings save flow. The canvas renderer should receive the selected mode and use the following palettes:

```ts
const WAVEFORM_PALETTES = {
  '3band': { low: '#0055e2', mid: '#f2aa3c', high: '#ffffff' },
  rgb: { low: '#ff304f', mid: '#35d07f', high: '#3d8bff' },
};
```

The RGB mode should use additive/lighter compositing so overlapping frequency energy creates blended colors. The 3Band mode should retain the current separate blue/orange/white presentation. The setting changes rendering only and must not re-run audio analysis.

## Error handling and compatibility

- A stream URL failure clears the active preview and displays the existing toast/error pattern.
- A metadata failure leaves audio playing and displays a non-blocking metadata warning or loading fallback.
- Cancelling a preview stops/ignores the previous metadata job result.
- The old combined endpoint remains callable for fallback and diagnostics.
- No download quality, preset selection, or bitrate verification behavior changes in this feature.

## Testing requirements

- Unit-test stateful chunk processing with chunks split inside waveform-pixel boundaries.
- Verify streaming and existing full-file waveform output are within an explicit tolerance for a deterministic fixture.
- Verify filter state persists across chunks and no boundary discontinuity is introduced.
- Verify metadata failure does not fail the stream path.
- Verify stale metadata cannot replace the currently selected track.
- Verify both color palettes render from the same band arrays and changing mode does not trigger an API request.
- Run the existing backend test suite and frontend build.
- Add a manual test with a multi-minute full track: click preview, confirm audio starts before metadata completes, seek during background analysis, then confirm the final waveform replaces the provisional state.

## Non-goals

- Rewriting wavypy in Rust, Go, C++, or another language before profiling proves CPU processing is the bottleneck.
- Building a backend media proxy/tee in this phase.
- Changing the selected preview quality away from the current low-quality preview behavior.
- Optimizing download speed by reducing quality, skipping ffprobe verification, or weakening the quality fallback ladder.

## Deferred download-speed research

Create a separate future plan that measures the download pipeline before changing it. It must investigate connection reuse, redundant requests, ffmpeg invocation overhead, temporary-file I/O, sequential queue behavior, and safe concurrency limits while preserving selected quality, ffprobe verification, format conversion correctness, and metadata integrity. Any proposed optimization must include before/after bitrate and output-integrity verification.
