# Search Improvements — Result Scoring + Metadata Enrichment

**Date:** 2026-06-19  
**Author:** felipecanas (via Claude)  
**Status:** Approved — ready for implementation

---

## Problem Statement

When searching for new releases or exact tracks, the Tidal search API returns results ordered by popularity rather than relevance or recency. This causes:

1. **Correct tracks buried** — New releases appear on page 2+ while older/popular tracks dominate page 1
2. **Missing remix info** — Track titles omit version/remix suffixes (e.g., `"What To Do"` instead of `"What To Do (&ME Remix)"`)
3. **Messy result lists** — Covers, remixes, live versions, and different artists clutter results

Users currently must go to Tidal's app/website to find the right track, then return to paste its URL.

---

## Goals

1. **Exact matches rank higher** — Searching `"Track Name - Artist"` surfaces the correct track in the top 3
2. **Complete titles** — Remix/version info appears in search results
3. **Graceful degradation** — If enrichment fails, search still returns usable results

## Non-Goals

- Pagination support (backend already returns limited results)
- Fuzzy matching or spell correction
- Album/playlist result scoring (focus on tracks only)

---

## Architecture

### Overview

```
Search Query (frontend)
       ↓
/search endpoint (backend/main.py)
       ↓
search_tidal() → raw results (backend/search.py)
       ↓
score_results() → sort by relevance (NEW)
       ↓
enrich_tracks(top 5) → add version/remix info (NEW)
       ↓
format_track() → JSON response
       ↓
Frontend renders enriched, sorted results
```

### Components

#### 1. Result Scoring (`score_results`)

**Location:** `backend/search.py`

**Signature:**
```python
def score_results(tracks: List, query: str, artist_filter: Optional[str] = None) -> List[Tuple[dict, float]]
```

**Scoring rules:**

| Criterion | Points |
|-----------|--------|
| Exact title match (query words in order) | +10 |
| Partial title match (any query word in title) | +5 |
| Released within 30 days | +5 |
| Exact artist match (when " - " in query) | +10 |

**Sort:** Descending by score. Tracks with equal score maintain relative order.

**Why this matters:** New releases with exact matches jump to the top, reducing time spent scrolling.

---

#### 2. Metadata Enrichment (`enrich_tracks`)

**Location:** `backend/search.py`

**Signature:**
```python
def enrich_tracks(session: tidalapi.Session, tracks: List[dict], top_n: int = 5) -> List[dict]
```

**Behavior:**

1. Take the top `N` tracks by score (default: 5)
2. For each, fetch the full `Track` object via `session.track(track_id)`
3. Construct complete title using priority:
   - `track.full_title` (if available)
   - `track.title + " (" + track.version + ")"` (if version exists)
   - `track.title` (fallback)
4. Replace the `title` field in the formatted dict

**Performance:** Runs in parallel via `asyncio.gather()` + `asyncio.to_thread()` (tidalapi is synchronous).

**Error handling:** If any enrichment call fails:
- Log warning with track ID and error
- Keep the original (unenriched) title
- Do NOT fail the entire search

**Why top 5 only:** Enriching all results would add too much latency. Top 5 captures the most relevant tracks while keeping response time under ~500ms overhead.

---

#### 3. Endpoint Changes (`/search`)

**Location:** `backend/main.py`

**Current:**
```python
results = await asyncio.to_thread(search_tidal, session, q, models, artist_filter=artist_filter)
return results
```

**Updated:**
```python
raw = await asyncio.to_thread(search_tidal, session, q, models, artist_filter=artist_filter)

# Score and sort tracks
if raw.get("tracks"):
    scored = score_results(raw["tracks"], q, artist_filter)
    raw["tracks"] = [t for t, _ in scored]  # strip scores

# Enrich top 5 titles
if raw.get("tracks"):
    raw["tracks"] = await asyncio.to_thread(enrich_tracks, session, raw["tracks"], 5)

return results
```

---

## Data Flow

```
User types: "What To Do - &ME"
         ↓
POST /search?q=What+To+Do+-+&ME&type=track
         ↓
search_tidal() → 50 tracks from Tidal API
         ↓
score_results() → Each track scored:
  - "What To Do (&ME Remix)" → title match +10, artist match +10 = 20
  - "What To Do (Original Mix)" → title match +10 = 10
  - Older tracks → lower scores
         ↓
Sort by score descending
         ↓
enrich_tracks(top 5) → Fetch full metadata:
  - Track 1: version = "(&ME Remix)" → title updated
  - Track 2-5: same process
         ↓
format_track() → JSON with enriched titles
         ↓
Frontend displays sorted results with complete titles
```

---

## Error Handling

| Failure Mode | Behavior |
|--------------|----------|
| Enrichment API timeout | Log warning, return original title |
| tidalapi exception on specific track | Log warning, skip that track, continue |
| Tidal session expired | Propagate 401 (existing auth flow handles) |
| Scoring fails (no tracks) | Return empty results (no-op) |

**Logging:** All enrichment failures logged at `WARNING` level with track ID and error message.

---

## Testing Strategy

### Unit Tests (`backend/tests/test_search.py`)

1. **`test_score_results_exact_match`** — Exact title + artist match scores highest
2. **`test_score_results_recency_boost`** — Track released 7 days ago scores higher than identical track from 1 year ago
3. **`test_enrich_tracks_adds_version`** — Track with `version` field gets `"Title (Version)"` format
4. **`test_enrich_tracks_silent_fallback`** — Failed enrichment returns original title, no exception

### Manual Testing

1. Search for a known new release (e.g., recent single)
2. Verify correct track appears in top 3
3. Verify remix/version info displays in title
4. Verify search still works if backend enrichment code throws (check logs)

---

## Migration Plan

**No migration required.** This is a pure code change:

1. No database schema changes
2. No config changes
3. No frontend changes (API response shape unchanged)

**Deployment:** Standard git push → restart backend.

---

## Success Criteria

- [ ] Correct track appears in **top 3** for exact searches
- [ ] Remix/version info visible in **≥80%** of enriched tracks
- [ ] Search latency increases by **<500ms** average
- [ ] Zero user-facing errors from enrichment failures

---

## Open Questions

None — design is complete and approved.

---

## Appendix: tidalapi Field Reference

Fields available from `tidalapi.Track`:

```python
track.title          # Basic title (often missing remix info)
track.version        # Version string (e.g., "&ME Remix")
track.full_title     # Full title if available (not always populated)
track.album.name     # Album name
track.artist.name    # Artist name
track.release_date   # datetime.date object
```

**Note:** `full_title` is not guaranteed — always fallback to constructing from `title + version`.