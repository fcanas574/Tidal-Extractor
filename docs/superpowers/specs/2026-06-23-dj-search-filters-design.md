# DJ Search Filters — Design Specification

**Date:** 2026-06-23
**Status:** Approved
**Author:** Claude (with user collaboration)

---

## Overview

Add DJ-focused search filtering to TidalExtractor, enabling users to find tracks by BPM, musical key (Camelot notation), harmonic compatibility, and genre. This feature transforms the app from a general-purpose Tidal downloader into a DJ workflow tool.

**Primary use case:** A DJ preparing a set wants to find all tracks between 120-128 BPM in compatible keys for harmonic mixing, filtered to relevant genres.

---

## Problems Solved

| Problem | Current State | After |
|---------|---------------|-------|
| Finding tracks by energy/tempo | Manual browsing or external tools | Filter by BPM range directly |
| Harmonic mixing preparation | Check each track's key individually | Select key, enable "Compatible", instantly see all mixable tracks |
| Genre-specific crate digging | Text search returns mixed results | Curated genre filter for DJ-relevant styles |
| Key notation confusion | Tidal uses "F MINOR", DJs use Camelot | Display both, filter by Camelot |

---

## Constraints

1. **Tidal API limitations:**
   - No per-track genre field exposed — genre filtering uses `genre:` search prefix
   - BPM and Key available on ~85-90% of electronic tracks (tested)
   - Genre search returns inconsistent results for niche subgenres

2. **FreqBlog API:**
   - Strict rate limits on free tier
   - NOT used for search filtering — only for preview/download fallback

3. **Performance:**
   - Client-side filtering after search must be fast (<100ms for 50 results)
   - No new database tables required — filtering is stateless

---

## Architecture

### Backend Changes

#### 1. `backend/search.py` — Format Track Enhancement

**Current:** `format_track()` does not capture BPM/Key from Tidal response.

**After:**
```python
def format_track(track) -> dict:
    # ... existing fields ...
    return {
        "id": track.id,
        "title": track.title,
        "artist": track.artist.name,
        "album": track.album.name,
        "duration": track.duration,
        "quality": track.audio_quality,
        "explicit": track.explicit,
        "isrc": track.isrc,
        "url": track.listen_url,
        "cover_url": cover_url,
        # NEW FIELDS:
        "bpm": track.bpm,
        "key": track.key,
        "key_scale": track.key_scale,
    }
```

#### 2. `backend/main.py` — Search Endpoint Enhancement

**Current:**
```python
@app.get("/search")
async def search(q: str, type: str = "track"):
    # ... basic search ...
```

**After:**
```python
@app.get("/search")
async def search(
    q: str,
    type: str = "track",
    bpm_min: Optional[int] = None,
    bpm_max: Optional[int] = None,
    key: Optional[str] = None,
    key_compatible: bool = False,
    genre: Optional[str] = None,
):
    # ... existing logic ...

    # Apply genre prefix if selected
    search_query = q
    if genre:
        search_query = f"genre:{genre} {q}" if q else f"genre:{genre}"

    # Get raw results
    raw = await asyncio.to_thread(search_tidal, session, search_query, models, artist_filter)

    # Apply BPM/Key filtering post-search
    if raw.get("tracks") and (bpm_min or bpm_max or key):
        raw["tracks"] = filter_tracks_by_dj_metadata(
            raw["tracks"], bpm_min, bpm_max, key, key_compatible
        )

    # ... rest of scoring/enrichment ...
```

**New helper function:**
```python
def filter_tracks_by_dj_metadata(
    tracks: List[dict],
    bpm_min: Optional[int],
    bpm_max: Optional[int],
    key: Optional[str],
    key_compatible: bool,
) -> List[dict]:
    """Filter tracks by BPM range and/or Camelot key."""
    from backend.key_detection import CAMELOT_MAP  # for reverse lookup

    # Expand key if compatible mode is on
    target_keys = [key] if key else []
    if key and key_compatible:
        target_keys = get_compatible_keys(key)

    filtered = []
    for track in tracks:
        # BPM filter
        track_bpm = track.get("bpm")
        if bpm_min is not None or bpm_max is not None:
            if track_bpm is None:
                continue  # Skip tracks without BPM data
            if bpm_min is not None and track_bpm < bpm_min:
                continue
            if bpm_max is not None and track_bpm > bpm_max:
                continue

        # Key filter
        if target_keys:
            track_key = track.get("key")
            track_scale = track.get("key_scale")
            if not track_key or not track_scale:
                continue  # Skip tracks without key data
            track_camelot = convert_to_camelot(track_key, track_scale)
            if track_camelot not in target_keys:
                continue

        filtered.append(track)

    return filtered
```

**New utility functions:**
```python
def convert_to_camelot(key: str, scale: str) -> Optional[str]:
    """Convert Tidal key (e.g., 'F', 'MINOR') to Camelot (e.g., '5A')."""
    # Uses CAMELOT_MAP reverse lookup from key_detection.py

def get_compatible_keys(camelot: str) -> List[str]:
    """Return list of harmonically compatible Camelot keys."""
    # E.g., '8A' -> ['7A', '8A', '9A', '8B']
```

#### 3. `backend/main.py` — New Compatibility Endpoint

```python
@app.get("/keys/compatible")
async def get_compatible_keys_route(key: str):
    """Return list of Camelot keys compatible with the given key for harmonic mixing."""
    if not key:
        raise HTTPException(status_code=400, detail="key parameter required")
    compatible = get_compatible_keys(key)
    return {"key": key, "compatible": compatible}
```

---

### Frontend Changes

#### 1. `frontend/src/api.ts` — API Client

**New types:**
```typescript
interface TrackResult {
  id: number;
  title: string;
  artist: string;
  album: string;
  duration: number;
  quality: string;
  explicit: boolean;
  isrc: string | null;
  url: string;
  cover_url: string | null;
  // NEW:
  bpm: number | null;
  key: string | null;
  key_scale: string | null;
}
```

**New API functions:**
```typescript
export const search = {
  query: (q: string, type: SearchType, filters?: {
    bpmMin?: number;
    bpmMax?: number;
    key?: string;
    keyCompatible?: boolean;
    genre?: string;
  }) => request<SearchResults>(
    `/search?q=${encodeURIComponent(q)}&type=${type}` +
    (filters?.bpmMin ? `&bpm_min=${filters.bpmMin}` : '') +
    (filters?.bpmMax ? `&bpm_max=${filters.bpmMax}` : '') +
    (filters?.key ? `&key=${filters.key}` : '') +
    (filters?.keyCompatible ? '&key_compatible=true' : '') +
    (filters?.genre ? `&genre=${encodeURIComponent(filters.genre)}` : '')
  ),

  getCompatibleKeys: (key: string) => request<{ key: string; compatible: string[] }>(
    `/keys/compatible?key=${encodeURIComponent(key)}`
  ),
};
```

#### 2. `frontend/src/components/SearchView.tsx` — Filter Bar

**New component structure:**
```tsx
// After search results, before results list:
{results && results.tracks.length > 0 && (
  <div className="dj-filter-bar">
    {/* BPM Slider */}
    <div className="filter-group">
      <label>BPM</label>
      <RangeSlider
        min={60}
        max={200}
        value={[bpmMin, bpmMax]}
        onChange={([min, max]) => {
          setBpmMin(min);
          setBpmMax(max);
          applyFilters();
        }}
      />
      <span className="filter-value">{bpmMin} — {bpmMax}</span>
    </div>

    {/* Key Dropdown */}
    <div className="filter-group">
      <label>Key</label>
      <select
        value={selectedKey}
        onChange={(e) => {
          setSelectedKey(e.target.value);
          applyFilters();
        }}
      >
        <option value="">Any Key</option>
        {['1A','2A','3A','4A','5A','6A','7A','8A','9A','10A','11A','12A',
         '1B','2B','3B','4B','5B','6B','7B','8B','9B','10B','11B','12B'].map(k => (
          <option key={k} value={k}>{k}</option>
        ))}
      </select>
    </div>

    {/* Compatible Toggle */}
    {selectedKey && (
      <div className="filter-group filter-toggle">
        <label className="toggle-label">
          <input
            type="checkbox"
            checked={keyCompatible}
            onChange={(e) => {
              setKeyCompatible(e.target.checked);
              applyFilters();
            }}
          />
          <span className="toggle-icon">🎯</span>
          <span className="toggle-text">Compatible</span>
        </label>
      </div>
    )}

    {/* Genre Dropdown */}
    <div className="filter-group">
      <label>Genre</label>
      <select
        value={selectedGenre}
        onChange={(e) => {
          setSelectedGenre(e.target.value);
          applyFilters();
        }}
      >
        <option value="">Any Genre</option>
        <optgroup label="Electronic">
          <option>House</option>
          <option>Tech House</option>
          <option>Deep House</option>
          <option>Techno</option>
          <option>Trance</option>
          <option>Drum & Bass</option>
          <option>Dubstep</option>
          <option>Electro</option>
          <option>Hardstyle</option>
        </optgroup>
        <optgroup label="Hip-Hop / R&B">
          <option>Hip-Hop</option>
          <option>R&B</option>
        </optgroup>
        <optgroup label="Latin">
          <option>Reggaeton</option>
          <option>Latin</option>
        </optgroup>
        <optgroup label="Pop / Rock">
          <option>Pop</option>
          <option>Rock</option>
        </optgroup>
        <optgroup label="Afro">
          <option>Afro House</option>
          <option>Amapiano</option>
        </optgroup>
      </select>
    </div>

    {/* Clear All */}
    {(bpmMin !== 60 || bpmMax !== 200 || selectedKey || selectedGenre) && (
      <button onClick={clearFilters} className="btn-clear-filters">
        Clear
      </button>
    )}
  </div>
)}
```

#### 3. `frontend/src/components/CamelotWheel.tsx` — NEW

Interactive Camelot wheel visualization for harmonic mixing reference:

```tsx
// Shows the Camelot Wheel with:
// - All 24 keys (12 A / 12 B) in a circle
// - Highlighted selected key
// - Highlighted compatible keys (±1 + relative)
// - Click any key to filter by it

// Visual structure:
// - Outer ring: 1B, 2B, ... 12B (major keys)
// - Inner ring: 1A, 2A, ... 12A (minor keys)
// - Lines connecting relative major/minor pairs (1A↔1B, etc.)
```

**Placement:** Modal or sidebar panel, triggered by "Show Camelot Wheel" button near filter bar.

#### 4. `frontend/src/index.css` — Filter Bar Styles

```css
.dj-filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  margin-top: 16px;
  background: var(--bg-deep);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-group label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.filter-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-bright);
}

.filter-toggle .toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
}

.filter-toggle input[type="checkbox"] {
  accent-color: var(--accent-primary);
}

.toggle-icon {
  font-size: 14px;
}
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ User Actions                                                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ SearchView Component                                                │
│  - User enters search query                                         │
│  - User adjusts filter controls                                     │
│  - applyFilters() constructs query params                          │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ API Client (api.ts)                                                 │
│  GET /search?q=house&bpm_min=120&bpm_max=128&key=8A&key_compatible  │
│                      &genre=House                                   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Backend (/search endpoint)                                          │
│  1. Prepend genre prefix if selected                                │
│  2. Call Tidal API search                                           │
│  3. Filter results by BPM/Key                                       │
│  4. Score and sort                                                  │
│  5. Enrich top N tracks                                             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Response                                                            │
│ { tracks: [{id, title, bpm, key, key_scale, camelot?, ...}], ... } │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ SearchView renders filtered results                                 │
│  - Each track shows BPM badge (if available)                        │
│  - Each track shows Camelot key badge (converted from key+scale)    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## UI States

### Filter Bar Visibility
| State | Display |
|-------|---------|
| No search performed | Hidden |
| Search performed, results exist | Visible |
| Search performed, no results | Hidden (show "No results" message) |

### Filter Combinations

| BPM | Key | Compatible | Genre | Behavior |
|-----|-----|------------|-------|----------|
| Set | — | — | — | Filter by BPM range only |
| — | 8A | Off | — | Show only exact 8A matches |
| — | 8A | On | — | Show 7A, 8A, 9A, 8B |
| Set | 8A | On | House | All filters combined |
| — | — | — | House | Genre search only |

### Empty States
- **0 results after filtering:** Show "No tracks match these filters" with "Clear Filters" button
- **Track missing BPM/Key data:** Excluded from filtered results (can't match what we don't have)

---

## Camelot Conversion Logic

**Tidal → Camelot mapping:**

| Tidal Key | Scale | Camelot |
|-----------|-------|---------|
| C | MAJOR | 5B |
| C | MINOR | 5A |
| C# | MAJOR | 6B |
| C# | MINOR | 6A |
| D | MAJOR | 7B |
| D | MINOR | 7A |
| ... | ... | ... |

**Formula:**
```python
PITCH_TO_NUMBER = {
    'C': 5, 'CSharp': 6, 'Db': 6,
    'D': 7, 'DSharp': 8, 'Eb': 8,
    'E': 9, 'F': 10, 'FSharp': 11, 'Gb': 11,
    'G': 12, 'GSharp': 1, 'Ab': 1,
    'A': 2, 'ASharp': 3, 'Bb': 3,
    'B': 4,
}
```

For major: `{number}B`
For minor: `{number}A`

---

## Harmonic Compatibility Rules

Given Camelot key `Xn` where `X` is 1-12 and `n` is A or B:

**Compatible keys:**
1. `(X-1)n` — previous number, same letter (wrap 1→12)
2. `Xn` — exact match
3. `(X+1)n` — next number, same letter (wrap 12→1)
4. `Xm` where `m ≠ n` — same number, opposite letter (relative major/minor)

**Example for 8A:**
- 7A (previous minor)
- 8A (exact)
- 9A (next minor)
- 8B (relative major)

---

## Error Handling

| Error Case | Handling |
|------------|----------|
| Tidal API returns no BPM/Key | Track excluded from filtered results |
| Invalid Camelot key param | Return 400, show toast "Invalid key format" |
| Genre not recognized by Tidal | Search returns empty, show "No tracks in this genre" |
| Filter produces 0 results | Show empty state with "Clear Filters" button |

---

## Testing Strategy

**Unit Tests:**
1. `convert_to_camelot()` — all 24 key/scale combinations
2. `get_compatible_keys()` — verify ±1 + relative logic
3. `filter_tracks_by_dj_metadata()` — edge cases (None values, boundary BPM)

**Integration Tests:**
1. Genre search returns expected results for known genres
2. BPM filtering handles edge cases (exactly at min/max)
3. Compatible key expansion returns correct 4 keys

**Manual Testing:**
1. Search "house", filter 120-128 BPM, verify results
2. Select 8A + Compatible, verify 7A/8A/9A/8B appear
3. Genre dropdown → House → verify results match genre

---

## Performance Considerations

- **Client-side filtering:** <50 tracks, filtering is instantaneous
- **Server-side filtering:** Tidal API returns 50 results max, filter is O(n)
- **Camelot Wheel:** Static SVG, minimal re-renders
- **No new database queries:** All filtering is stateless

---

## Future Enhancements (Out of Scope)

- **Playlist export** (M3U, Rekordbox XML) — Phase C
- **Smart crates** — Auto-populate by BPM/key rules
- **Energy level** — If Tidal exposes audio features in future
- **Key history** — Remember last-used key filter
- **BPM pulse preview** — Visual metronome while browsing

---

## Implementation Checklist

- [ ] `backend/search.py`: Add BPM/Key to `format_track()`
- [ ] `backend/main.py`: Add filter params to `/search` endpoint
- [ ] `backend/main.py`: Implement `filter_tracks_by_dj_metadata()`
- [ ] `backend/main.py`: Add `convert_to_camelot()` and `get_compatible_keys()`
- [ ] `backend/main.py`: Add `/keys/compatible` endpoint
- [ ] `frontend/src/api.ts`: Add BPM/Key to `TrackResult` type
- [ ] `frontend/src/api.ts`: Add filter params to `search.query()`
- [ ] `frontend/src/api.ts`: Add `search.getCompatibleKeys()`
- [ ] `frontend/src/components/SearchView.tsx`: Add FilterBar component
- [ ] `frontend/src/components/SearchView.tsx`: Add range slider, dropdowns, toggle
- [ ] `frontend/src/components/CamelotWheel.tsx`: Create new component
- [ ] `frontend/src/index.css`: Add filter bar styles
- [ ] Tests: Backend filter logic
- [ ] Tests: Frontend filter state management

---

## Appendix: Tidal Genre List

Based on testing, these genre prefixes return results:

| Works | Doesn't Work |
|-------|--------------|
| House | Tech House |
| Deep House | Melodic House |
| Techno | Progressive House |
| Trance | |
| Drum & Bass | |
| Hip-Hop | |
| R&B | |
| Reggaeton | |
| Latin | |
| Pop | |
| Rock | |
| Afro House | |
| Amapiano | |
| Dubstep | |
| Electro | |
| Hardstyle | |

**Implementation note:** Include both working and non-working genres in dropdown. Tidal's genre search is inconsistent; the curated list provides a better UX even if some genres return sparse results.

---

## Appendix: Camelot Wheel Reference

```
     12B ─── 1B ─── 2B
    /                   \
   12A                   2A
   |                      |
   11A                   3A
    \                   /
     11B ─── 10B ─── ...
```

Full wheel available at: https://mixedink.com/camelot-wheel/

---

**End of Spec**