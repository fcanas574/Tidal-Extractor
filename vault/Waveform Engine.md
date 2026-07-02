# Waveform Engine

Generates tri-band (lows/mids/highs) waveforms for the preview player using the **wavypy** submodule, with compatibility shims for Python 3.13+.

**See:** [[Backend waveform]] · [[Backend audioop_stub]] · [[Components]]

## Purpose

The `AudioPlayerFooter` renders a Rekordbox-style 3-band waveform when a user previews a track. Each band (low/mid/high frequencies) is a normalized amplitude envelope over ~600 points, drawn on a `<canvas>` with distinct colors.

## The Pipeline

```
GET /preview/{track_id}
  → session.track(id).get_url() [quality temporarily set to LOW]
  → get_waveform_cached(stream_url)        # @lru_cache(64)
      │
      │ cache MISS:
      ▼
  build_waveform(stream_url):
    1. ffmpeg -i <url> → tmp.wav (mono, 44100Hz, pcm_s16le)
    2. _run_wavypy(tmp.wav, tmp.json, band_preset="club", width=600):
         a. Spawn subprocess running a generated Python script:
            - Install audioop_stub into sys.modules (pydub compat)
            - Monkey-patch pydub.AudioSegment → FakeAudioSegment (scipy-backed)
            - Import wavypy, run generate_waveform_data(BASE64_JSON, NONE)
            - save_as_json(bits=2 / SIXTEEN)
            - Reload JSON, base64-decode each band's samples → plain arrays
         b. Return True/False
    3. Parse multiband JSON:
         for each band (low/mid/high):
           samples = [min0,max0,min1,max1,...] int16 pairs
           RMS per pair = abs(hi - lo) / 65536.0
           normalize → [0,1] by dividing by max
    4. Return { bands: {low,mid,high}, duration }
  → cached
  → return { bands, colors: {low,mid,high}, duration }
```

## Output Shape (`WaveformData`)

```typescript
{
  bands: {
    low:  number[],   // ~600 normalized [0,1] points
    mid:  number[],
    high: number[],
  },
  colors: { low: "#0055e2", mid: "#f2aa3c", high: "#ffffff" },
  duration: number,   // seconds (default 30)
}
```

## Why wavypy + "club" preset

wavypy (from GabrielJuliao/wavypy) implements proper band-splitting filters with correct slopes. The **"club"** preset uses 3 bands tuned for electronic music — the primary use case given the [[DJ Filters]]. The DJ can see where the kick (low), melodic content (mid), and hats (high) sit.

## Compatibility Layer

Two shims make this work on Python 3.13+:

1. **`audioop_stub`** — provides the removed `audioop` module so pydub imports succeed (see [[Backend audioop_stub]])
2. **`FakeAudioSegment`** — replaces `pydub.AudioSegment` entirely, reading WAV via `scipy.io.wavfile`. This bypasses pydub's ffmpeg dependency for decoding — wavypy only needs the sample array + frame rate.

Both are injected in the subprocess script before wavypy is imported.

## Caching

`get_waveform_cached` uses `@lru_cache(maxsize=64)` keyed by **stream URL**.

**Caveat:** Tidal stream URLs can rotate, so the cache may miss for the same track across sessions or after URL expiry. Within a session, repeat previews of the same track are instant.

## Performance

- First preview: ffmpeg decode (~1s) + wavypy analysis (~1-3s) = a few seconds
- Cached previews: instant (in-process dict lookup)
- All work offloaded to a thread (`asyncio.to_thread`) to avoid blocking the event loop

## Frontend Rendering

`AudioPlayerFooter.tsx` draws each band as a vertical bar sequence on a `<canvas>`:
- X-axis = time (band array index)
- Y-axis = amplitude (normalized value)
- Colors per band (blue/amber/white)
- Click-to-seek, play/pause, rainbow Camelot animation during playback

## Failure Modes

- ffmpeg download fails (returncode != 0 or tiny file) → returns `{}`
- wavypy subprocess fails → returns `{}`
- Non-multiband output → returns `{}`
- Any exception → returns `{}`

On failure, the frontend gets an empty waveform and the player still works (just without the visualization).

## See Also

- [[Backend waveform]] · [[Backend audioop_stub]] · [[Components]] · [[Key Detection]]
