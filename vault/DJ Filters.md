# DJ Filters

Harmonic-mixing-oriented search filtering: BPM range, Camelot key, harmonic compatibility, and genre browsing.

**See:** [[Search Subsystem]] · [[Backend key_detection]] · [[Backend main]] · [[Components]]

## Overview

Implemented 2026-06-23 (see [[Work Log]]). Enables DJs to find tracks that mix harmonically — same key, adjacent keys, or relative major/minor — filtered by tempo and genre.

## The Four Filters

### 1. BPM Range (`bpm_min`, `bpm_max`)
- Two inputs, 60–200 BPM
- Tracks with `bpm is None` are **excluded** when either bound is set
- Inclusive on both ends

### 2. Camelot Key (`key`)
- Dropdown of all 24 keys: 1A–12A, 1B–12B
- Tracks missing `key` or `key_scale` are excluded
- Converted via `convert_to_camelot(track.key, track.key_scale)` then checked for membership

### 3. Harmonic Compatibility (`key_compatible`)
- Toggle: when on, expands the selected key to its compatible set via `get_compatible_keys()`
- For `8A` → includes `7A, 8A, 9A, 8B`
- **Rules:** ±1 same letter + same number opposite letter (relative major/minor)

### 4. Genre (`genre`)
- Dropdown of 17 curated genres (House, Techno, Trance, Drum & Bass, etc.)
- Allows searching **without a text query** (empty `q` + `genre`)
- Backend constructs `genre:{genre}` prefix for Tidal's search syntax

## Backend: `filter_tracks_by_dj_metadata()` (`main.py:124`)

```python
target_keys = [key] if key else []
if key and key_compatible:
    target_keys = get_compatible_keys(key)   # expand

for track in tracks:
    # BPM filter
    if bpm_min or bpm_max:
        if track.bpm is None: skip
        if bpm_min and track.bpm < bpm_min: skip
        if bpm_max and track.bpm > bpm_max: skip
    # Key filter
    if target_keys:
        if not track.key or not track.key_scale: skip
        camelot = convert_to_camelot(track.key, track.key_scale)
        if camelot not in target_keys: skip
    keep(track)
```

**Critical:** Runs on the **full cached result set** BEFORE pagination slicing (see [[Search Subsystem]]).

## Camelot Conversion

Tidal returns keys like `'C'`, `'CSharp'`, `'Db'`, `'F'` and scales `'MAJOR'`/`'MINOR'`. `convert_to_camelot()` maps via the Circle of Fifths:

```python
PITCH_TO_CAMELOT_NUM = {
    'Ab':1, 'GSharp':1, 'Eb':2, 'DSharp':2, 'Bb':3, 'ASharp':3,
    'F':4, 'C':5, 'G':6, 'D':7, 'A':8, 'E':9, 'B':10,
    'FSharp':11, 'Gb':11, 'Db':12, 'CSharp':12,
}
letter = 'B' if MAJOR else 'A'
return f"{number}{letter}"
```

**Verified mappings:** C MINOR→5A, F MINOR→4A, GSharp MAJOR→1B, Db MAJOR→12B.

## Harmonic Compatibility Rules

For Camelot key `Xn` (X=1–12, n=A or B):
| Relation | Result |
|----------|--------|
| Previous, same letter | `(X-1)n` (wrap 1→12) |
| Exact | `Xn` |
| Next, same letter | `(X+1)n` (wrap 12→1) |
| Relative major/minor | `X(opposite)` |

```
8A  → ['7A', '8A', '9A', '8B']
1B  → ['12B', '1B', '2B', '1A']
12A → ['11A', '12A', '1A', '12B']
```

## Frontend UX

### SearchView layout
- **Genre dropdown** in the search header (always visible — enables empty-query searches)
- **Filter bar** appears only when results exist
  - BPM min/max inputs
  - Camelot key dropdown (1A–12B)
  - 🎯 Compatible toggle
  - Clear button (resets all filters + pagination)

### Track badges (always shown when metadata present)
- **Amber BPM badge** — rounded BPM value
- **Cyan Camelot badge** — key notation (e.g., "8A")
- Client-side `toCamelot()` helper converts for display

### Example workflow
1. Select "House" genre → Search with empty text
2. Set BPM 120–128
3. Select "8A" + enable Compatible
4. Results show 7A/8A/9A/8B tracks in 120–128 BPM — ready to mix

## Known Limitations

| Limitation | Impact |
|------------|--------|
| Tidal BPM/Key ~87% coverage on electronic | Some tracks lack badges / are filtered out |
| Genre prefix syntax (`genre:X`) | Subgenres like "Tech House" may not work |
| No client-side BPM/Key caching | Re-fetched each search |
| Filters NOT in cache key | Filter changes re-slice same results (fast, but no re-fetch) |

## Endpoints

- `GET /search` — accepts `bpm_min, bpm_max, key, key_compatible, genre`
- `GET /keys/compatible?key=8A` — returns `['7A','8A','9A','8B']`

## Deferred Work (Phase C)

User deferred DJ export features ("A and B first"):
- [ ] M3U playlist export
- [ ] Rekordbox XML export
- [ ] Serato export format
- [ ] Export only filtered tracks

See [[Roadmap]].

## See Also

- [[Search Subsystem]] · [[Backend key_detection]] · [[Backend main]] · [[Work Log]]
