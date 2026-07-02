# Search Pagination — "Load More" Design

**Date:** 2026-06-23  
**Status:** Approved  
**Related:** DJ Search Filters (`2026-06-23-dj-search-filters-design.md`)

---

## Problem

The current search returns up to 50 results with no way to access more. Users cannot browse beyond the initial batch, limiting discovery for popular queries (e.g., "House", "Techno").

---

## Solution

Implement a **"Load More"** button that fetches additional results without duplicates. Key guarantee: **users never see the same track twice**.

---

## Architecture

### Backend

| Component | Change |
|-----------|--------|
| `/search` endpoint | Add `offset: int = 0` parameter |
| Deduplication cache | In-memory `seen_track_ids` per query hash |
| Response | Return only *new* tracks not in previous loads |

### Frontend

| Component | Change |
|-----------|--------|
| `SearchView.tsx` | Track `loadedCount`, `hasMore` state |
| Results rendering | Append new tracks (not replace) |
| "Load More" button | Show when `hasMore = true` |

---

## Data Flow

```
1. Initial search: GET /search?q=House&offset=0&limit=50
   → Returns tracks 0-49
   
2. User clicks "Load More": GET /search?q=House&offset=50&limit=50
   → Backend filters out IDs 0-49, returns NEW tracks only
   
3. Frontend appends results, updates loadedCount to 100

4. Repeat until backend returns < 50 tracks (exhausted)
```

---

## Deduplication Logic

### Cache Key Generation

```python
cache_key = f"{query}:{bpm_min}:{bpm_max}:{key}:{genre}"
```

Changes to any filter = new cache entry = fresh results.

### Filtering

```python
# Before returning
new_tracks = [t for t in raw_results if t.id not in seen_ids]

# After returning
seen_ids.update(t.id for t in new_tracks)
```

---

## API Contract

### Request

```typescript
GET /search?q=House&type=track&offset=50&limit=50&bpm_min=120&bpm_max=128
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | `""` | Search query |
| `type` | string | `"track"` | Result type |
| `offset` | int | `0` | Tracks already loaded |
| `limit` | int | `50` | Batch size |
| `bpm_min` | int? | `null` | DJ filter |
| `bpm_max` | int? | `null` | DJ filter |
| `key` | string? | `null` | Camelot key |
| `genre` | string? | `null` | Genre filter |

### Response

```typescript
{
  tracks: TrackResult[];      // New tracks only (no duplicates)
  albums: AlbumResult[];
  playlists: PlaylistResult[];
}
```

---

## UI States

| State | Button Display |
|-------|----------------|
| Has more results | `"Load {n} more"` (clickable) |
| Loading | `"Loading..."` (disabled, spinner) |
| Exhausted | Hidden |
| Error | `"Failed to load — Retry"` |

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| User clears search | Reset `loadedCount`, clear cache |
| User changes filters | New query = new cache, start fresh |
| Tidal returns same results | Backend returns empty after first load |
| Network error | Show retry, don't increment counter |

---

## Implementation Notes

1. **In-memory cache only** — No persistence needed, resets on server restart
2. **Per-query isolation** — Different queries maintain separate seen sets
3. **Frontend owns count** — Backend just filters; frontend tracks `loadedCount`
4. **Batch size = 50** — Matches Tidal's default, reduces API calls

---

## Files to Modify

| File | Changes |
|------|---------|
| `backend/main.py` | Add `offset` param to `/search`, implement dedup cache |
| `frontend/src/api.ts` | Add `offset` to `search.query()` signature |
| `frontend/src/components/SearchView.tsx` | Add `loadedCount`/`hasMore` state, "Load More" button |

---

## Success Criteria

- [ ] "Load More" button appears after initial results
- [ ] Clicking appends new tracks without duplicates
- [ ] Button hides when no more results
- [ ] Changing filters resets pagination
- [ ] Retry works on network error

---

## Out of Scope

- Page numbers (offset-based navigation)
- Infinite scroll (auto-load on scroll)
- Cursor-based pagination (requires Tidal API changes)