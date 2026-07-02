# Backend: key_detection.py

**Role:** Musical key + BPM detection from audio via **librosa** chroma features, with Camelot Wheel mapping and harmonic compatibility logic.

**See:** [[Key Detection]] · [[DJ Filters]]

## Camelot Wheel Map

```python
CAMELOT_MAP = {
    "Ab minor": "1A", "Eb minor": "2A", "Bb minor": "3A", "F minor": "4A",
    "C minor": "5A", "G minor": "6A", "D minor": "7A", "A minor": "8A",
    "E minor": "9A", "B minor": "10A", "F# minor": "11A", "Db minor": "12A",
    "Ab major": "1B", "Eb major": "2B", "Bb major": "3B", "F major": "4B",
    "C major": "5B", "G major": "6B", "D major": "7B", "A major": "8B",
    "E major": "9B", "B major": "10B", "F# major": "11B", "Db major": "12B",
}
```

Based on the Circle of Fifths. Minor keys → `A` suffix, major → `B` suffix.

## Temperley Key Profiles

Pop/rock-optimized profiles used for chroma correlation:
```python
MAJOR_PROFILE = [5.61, 1.72, 3.67, 1.97, 4.99, 3.99, 1.79, 5.21, 2.30, 3.50, 2.06, 3.17]
MINOR_PROFILE = [5.79, 1.73, 3.97, 4.42, 1.76, 3.63, 1.98, 5.01, 3.82, 2.07, 3.51, 2.08]
```

## `detect_key(audio_path, sample_rate=22050)` → dict

```
1. librosa.load(path, sr=22050, mono=True)
2. chroma_cqt(y, sr, hop_length=512)         # Constant-Q chromagram
3. _estimate_key(chroma):
     - Mean chroma across time, normalize
     - For each of 12 shifts: dot product with MAJOR_PROFILE and MINOR_PROFILE
     - Pick best major vs best minor → key_name, mode, confidence
4. Look up CAMELOT_MAP[key_full], else compute via _CAMELOT_NUMBERS
5. librosa.beat.beat_track(y, sr) → tempo → bpm
```

Returns:
```python
{ key: "Am" | "C" | ...,      # " major"/" minor" stripped, minor→"m"
  camelot: "8A" | "5B" | ...,
  bpm: 120.0,
  confidence: 0.65 }
```

## `_estimate_key(chroma)` → `(key_full, mode, confidence)`

```python
chroma_avg = mean(chroma, axis=1); normalize
for shift in 0..11:
    major_scores[shift] = dot(roll(chroma_avg, shift), MAJOR_PROFILE)
    minor_scores[shift] = dot(roll(chroma_avg, shift), MINOR_PROFILE)
best_major = max(major_scores); best_minor = max(minor_scores)
if best_major > best_minor: key = PITCH_NAMES[idx], mode="major"
else:                        key = PITCH_NAMES[idx], mode="minor"
confidence = winner / (best_major + best_minor)
```

## `convert_to_camelot(key, scale)` → str

Converts **Tidal's** key notation to Camelot. Tidal returns keys like `'C'`, `'CSharp'`, `'Db'`, `'F'` and scales `'MAJOR'`/`'MINOR'`.

```python
PITCH_TO_CAMELOT_NUM = {
    'Ab':1,'GSharp':1, 'Eb':2,'DSharp':2, 'Bb':3,'ASharp':3,
    'F':4, 'C':5, 'G':6, 'D':7, 'A':8, 'E':9, 'B':10,
    'FSharp':11,'Gb':11, 'Db':12,'CSharp':12,
}
number = PITCH_TO_CAMELOT_NUM.get(key_normalized)
    # fallback: try {'C#':6,'D#':8,'F#':11,'G#':1,'A#':3}
letter = 'B' if MAJOR else 'A'
return f"{number}{letter}"
```

Returns `None` for unrecognized keys.

## `get_compatible_keys(camelot)` → list

Harmonic mixing rules for Camelot key `Xn` (X=1–12, n=A or B):
- Previous number, same letter: `(X-1)n` (wrap 1→12)
- Exact match: `Xn`
- Next number, same letter: `(X+1)n` (wrap 12→1)
- Relative major/minor: `X(opposite_letter)`

**Examples:**
- `8A` → `['7A', '8A', '9A', '8B']`
- `1B` → `['12B', '1B', '2B', '1A']`
- `12A` → `['11A', '12A', '1A', '12B']`

Wrapping math: `prev = ((X - 2) % 12) + 1`, `next = (X % 12) + 1`.

## `file_hash(path)` → str

MD5 of file content, truncated to 16 hex chars. Used as `key_cache` PK.

## Hybrid Strategy (in `main.py:_detect_preview_key`)

Previews use a 3-tier strategy — this module is the **fallback** tier:
1. `key_cache` table (by `preview_key_{track_id}`)
2. **FreqBlog API** (fast, no audio download) — [[Backend freqblog]]
3. **`detect_key()`** (this module, librosa, downloads full preview)

## See Also

- [[Key Detection]] · [[Backend freqblog]] · [[DJ Filters]] · [[Backend tagger]]
