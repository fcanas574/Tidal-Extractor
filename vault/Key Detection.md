# Key Detection

Musical key + BPM detection using a **hybrid** strategy: cache → FreqBlog API → local librosa analysis. Output is Camelot notation for DJs.

**See:** [[Backend key_detection]] · [[Backend freqblog]] · [[DJ Filters]]

## The Hybrid Strategy (Previews)

`_detect_preview_key()` in `main.py` is the orchestration point:

```
┌─────────────────────────────────────────────────────────┐
│  1. key_cache table (by "preview_key_{track_id}")        │  ~0ms
│     HIT → return {key, camelot, bpm}                     │
└─────────────────────────────────────────────────────────┘
                          │ MISS
                          ▼
┌─────────────────────────────────────────────────────────┐
│  2. FreqBlog API (lookup_track_metadata)                 │  ~100ms
│     HIT → cache + return                                 │
│     (no audio download — pure metadata lookup)           │
└─────────────────────────────────────────────────────────┘
                          │ MISS / no API key
                          ▼
┌─────────────────────────────────────────────────────────┐
│  3. Local librosa analysis (detect_key)                  │  ~seconds
│     Download full preview stream → tmp.mp4               │
│     chroma_cqt + Temperley profiles → key                │
│     beat_track → BPM                                     │
│     cache + return                                       │
└─────────────────────────────────────────────────────────┘
```

Each tier caches its result in the `key_cache` table, so subsequent previews of the same track are instant.

## Post-Download Detection

When a track finishes downloading (`download_track`), key detection runs on the **final local file** (not a preview stream):

```
key_result = detect_key(final_path)              # librosa
h = file_hash(final_path)                        # MD5[:16] of file content
db.set_key_cache(h, key, camelot, confidence, bpm)
tag_key(final_path, key, camelot)                # embed initialkey + camelot tags
```

This is **always local** (no FreqBlog) because the full file is already on disk. Failures are swallowed (download succeeds without key tags).

## Local Analysis: How It Works (`detect_key`)

1. `librosa.load(path, sr=22050, mono=True)`
2. `chroma_cqt(y, sr, hop_length=512)` — Constant-Q chromagram (12 bins, one per pitch class)
3. **Temperley profile correlation:**
   - Average chroma over time, normalize
   - For each of 12 rotations: dot product with MAJOR_PROFILE and MINOR_PROFILE
   - Best major vs best minor → key + mode + confidence
4. **Camelot mapping:** `CAMELOT_MAP["A minor"] = "8A"` (direct lookup), with `_CAMELOT_NUMBERS` fallback
5. **BPM:** `librosa.beat.beat_track(y, sr)` → tempo

Output: `{ key: "Am", camelot: "8A", bpm: 120.0, confidence: 0.65 }`

## Temperley Profiles

Pop/rock-optimized key profiles (vs. Krumhansl-Schmuckler). Better for the electronic music the DJ features target.

```python
MAJOR_PROFILE = [5.61, 1.72, 3.67, 1.97, 4.99, 3.99, 1.79, 5.21, 2.30, 3.50, 2.06, 3.17]
MINOR_PROFILE = [5.79, 1.73, 3.97, 4.42, 1.76, 3.63, 1.98, 5.01, 3.82, 2.07, 3.51, 2.08]
```

## Camelot Wheel

The Camelot system maps keys to number+letter codes for harmonic mixing:
- **Number 1–12:** position on the Circle of Fifths (Ab=1, Eb=2, ... Db=12)
- **Letter A:** minor key
- **Letter B:** major key

Compatible keys (see [[DJ Filters]]): ±1 same letter, or same number opposite letter.

## Confidence

`confidence = winner_score / (best_major + best_minor)` — how decisively the key beat the alternative mode. Low confidence (~0.5) means major/minor were ambiguous.

## Stats Tracking

`main.py:freqblog_stats` counts `{hits, misses, errors, cache_hits}`. Exposed via `GET /freqblog/stats`:
```python
hit_rate = hits / max(hits + misses, 1)
```

## Tidal Metadata (alternative source)

Tidal's API also returns `bpm`, `key`, `key_scale` per track (surfaced in `format_track`). This is used for **search filtering** ([[DJ Filters]]) without any audio analysis. Coverage is ~87% on electronic music. The librosa/FreqBlog path is for **previews and downloads** where you want independent verification or Tidal lacks the data.

## See Also

- [[Backend key_detection]] · [[Backend freqblog]] · [[DJ Filters]] · [[Backend tagger]]
