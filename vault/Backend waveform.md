# Backend: waveform.py

**Role:** Generates tri-band (lows/mids/highs) waveforms for the preview player by shelling out to the **wavypy** submodule, with a pydub→scipy compatibility shim.

**See:** [[Waveform Engine]] · [[Backend audioop_stub]]

## The Problem It Solves

The preview player (`AudioPlayerFooter.tsx`) renders a Rekordbox-style 3-band waveform. wavypy generates multiband waveform JSON, but:
1. wavypy depends on **pydub**, which depends on the removed `audioop` stdlib module (gone in Python 3.13+)
2. wavypy returns base64-encoded samples that need decoding to plain arrays for the frontend

This module bridges both issues by generating a self-contained Python script and running it in a subprocess.

## `_run_wavypy(audio_path, output_path, band_preset, width)` → bool

Builds a Python program as a string and executes it via `subprocess`:

1. **Patches `audioop`:** inserts `audioop_stub` into `sys.modules['audioop']` and `sys.modules['pyaudioop']` before pydub imports
2. **Monkey-patches `pydub.AudioSegment`:** replaces it with a `FakeAudioSegment` backed by `scipy.io.wavfile` (no ffmpeg/pydub audio decoding needed)
3. **Imports wavypy:** `from wavy import read_audio_file, generate_waveform_data, get_band_preset`
4. **Generates:** calls `generate_waveform_data(audio, sample_format=0 (BASE64_JSON), compression=0 (NONE))` with a fake `_SF` object controlling samples-per-pixel
5. **Saves:** `waveform.save_as_json(output_path, bits=2)` (SIXTEEN)
6. **Decodes:** reloads the JSON, base64-decodes each band's `samples` back to plain arrays, rewrites the file

Timeout: 60s. `PYTHONPATH` set to `WAVYPY_DIR`. Returns `False` on failure (logs first 500 chars of stderr).

## `build_waveform(stream_url)` → dict

```
1. Download full preview audio → tmp .wav via ffmpeg (mono, 44100Hz, pcm_s16le)
2. _run_wavypy(tmp_audio, tmp_json, band_preset="club", width=600)
3. Load JSON, expect type == "multiband"
4. For each band (low/mid/high):
     samples are [min0,max0,min1,max1,...] int16 pairs
     compute RMS per pair: abs(hi - lo) / 65536.0
     normalize to [0,1] by dividing by max
5. Return { bands: {low, mid, high}, duration }
```

Returns `{}` on any failure (download fail, non-multiband output, exception).

## `get_waveform_cached(stream_url)` → dict

`@lru_cache(maxsize=64)` — caches the *computed* waveform per stream URL in-process.

Returns:
```python
{ bands: {...}, colors: { low: "#0055e2", mid: "#f2aa3c", high: "#ffffff" }, duration }
```

## Integration

- `/preview/{track_id}` in `main.py` calls `get_waveform_cached(url)` in a thread
- The returned `bands` (3 arrays of normalized floats, ~600 points each) drive the canvas rendering in `AudioPlayerFooter.tsx`

## Why "club" preset

wavypy's `club` preset uses 3 bands with proper filter slopes suited to electronic music — the primary use case given the [[DJ Filters]].

## Gotchas

- The LRU cache is keyed by **stream URL**, not track ID. Tidal stream URLs may rotate/expire, potentially causing cache misses or stale entries over long sessions.
- Subprocess overhead per uncached preview (~wavypy analysis time + ffmpeg decode)
- `FakeAudioSegment` hardcodes `sample_width=2` (s16le) — matches the ffmpeg output format

## See Also

- [[Waveform Engine]] · [[Backend audioop_stub]] · [[Backend main]]
