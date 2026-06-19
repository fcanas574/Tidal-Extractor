# Search Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Tidal search results by sorting by relevance/recency and enriching top 5 results with complete track titles (including remix/version info).

**Architecture:** Add two new functions to `backend/search.py` — `score_results()` for ranking and `enrich_tracks()` for metadata enrichment. Modify `/search` endpoint in `backend/main.py` to call these functions.

**Tech Stack:** Python 3.13+, FastAPI, tidalapi, asyncio, pytest

## Global Constraints

- Enrich only top 5 results (not all)
- Enrichment failures must silently fallback (log warning, keep original title)
- No frontend changes required (API response shape unchanged)
- All new code must have test coverage in `backend/tests/test_search.py`

---

### Task 1: Add Result Scoring Function (`score_results`)

**Files:**
- Modify: `backend/search.py`
- Test: `backend/tests/test_search.py`

**Interfaces:**
- Consumes: `format_track()` output (dict with `title`, `artist`, `album`, etc.)
- Produces: `score_results(tracks: List[dict], query: str, artist_filter: Optional[str]) -> List[Tuple[dict, float]]`

- [ ] **Step 1: Add scoring imports to `backend/search.py`**

Add at top of file:
```python
from datetime import date, timedelta
from typing import List, Tuple, Optional
```

- [ ] **Step 2: Add `score_results()` function to `backend/search.py`**

Add after `format_track()` function:
```python
def score_results(tracks: List[dict], query: str, artist_filter: Optional[str] = None) -> List[Tuple[dict, float]]:
    """
    Score and sort search results by relevance.
    
    Scoring rules:
    - Exact title match (query words in order): +10
    - Partial title match (any query word in title): +5
    - Released within 30 days: +5
    - Exact artist match (when " - " in query): +10
    """
    scored = []
    query_lower = query.lower()
    query_words = query_lower.split()
    today = date.today()
    
    for track in tracks:
        score = 0.0
        title_lower = track.get("title", "").lower()
        artist_lower = track.get("artist", "").lower()
        
        # Exact title match (query appears in order)
        if query_lower in title_lower:
            score += 10.0
        # Partial title match (any word matches)
        elif any(word in title_lower for word in query_words if len(word) > 2):
            score += 5.0
        
        # Recency boost (released within 30 days)
        release_date = track.get("release_date")
        if release_date:
            try:
                release = date.fromisoformat(str(release_date))
                if (today - release).days <= 30:
                    score += 5.0
            except (ValueError, TypeError):
                pass
        
        # Exact artist match (when using "track - artist" format)
        if artist_filter and artist_filter.lower() in artist_lower:
            score += 10.0
        
        scored.append((track, score))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
```

- [ ] **Step 3: Add unit tests for `score_results()`**

Create/modify `backend/tests/test_search.py`:
```python
from datetime import date, timedelta
from backend.search import score_results


def test_score_results_exact_title_match():
    tracks = [
        {"title": "Abyss", "artist": "Orgyia", "release_date": None},
        {"title": "Abyss (Live)", "artist": "Other", "release_date": None},
    ]
    scored = score_results(tracks, "Abyss")
    # First track has exact match, should score highest
    assert scored[0][0]["title"] == "Abyss"
    assert scored[0][1] > scored[1][1]


def test_score_results_recency_boost():
    old_track = {"title": "Song", "artist": "Artist", "release_date": (date.today() - timedelta(days=365)).isoformat()}
    new_track = {"title": "Song", "artist": "Artist", "release_date": (date.today() - timedelta(days=7)).isoformat()}
    
    scored = score_results([old_track, new_track], "Song")
    # New track should score higher due to recency boost
    assert scored[0][0]["release_date"] == new_track["release_date"]


def test_score_results_artist_filter():
    tracks = [
        {"title": "Track", "artist": "Target Artist", "release_date": None},
        {"title": "Track", "artist": "Other Artist", "release_date": None},
    ]
    scored = score_results(tracks, "Track - Target", artist_filter="Target Artist")
    # Exact artist match should win
    assert scored[0][0]["artist"] == "Target Artist"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
python3 -m pytest backend/tests/test_search.py::test_score_results_exact_title_match -v
python3 -m pytest backend/tests/test_search.py::test_score_results_recency_boost -v
python3 -m pytest backend/tests/test_search.py::test_score_results_artist_filter -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add backend/search.py backend/tests/test_search.py
git commit -m "feat: add result scoring function for search ranking"
```

---

### Task 2: Add Metadata Enrichment Function (`enrich_tracks`)

**Files:**
- Modify: `backend/search.py`
- Test: `backend/tests/test_search.py`

**Interfaces:**
- Consumes: `session.track(track_id)` from tidalapi, scored track list
- Produces: `enrich_tracks(session, tracks, top_n=5) -> List[dict]` with enriched `title` fields

- [ ] **Step 1: Add `enrich_tracks()` function to `backend/search.py`**

Add after `score_results()`:
```python
def enrich_tracks(session, tracks: List[dict], top_n: int = 5) -> List[dict]:
    """
    Enrich top N tracks with full metadata (version/remix info).
    
    For each track, fetch the full Track object and construct complete title:
    1. track.full_title (if available)
    2. track.title + " (" + track.version + ")" (if version exists)
    3. track.title (fallback)
    
    Failures are silent — log warning and keep original title.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Only enrich top N tracks
    to_enrich = tracks[:top_n]
    remainder = tracks[top_n:]
    enriched = []
    
    for track_dict in to_enrich:
        track_id = track_dict.get("id")
        if not track_id:
            enriched.append(track_dict)
            continue
        
        try:
            full_track = session.track(track_id)
            new_title = track_dict.get("title", "")
            
            # Priority 1: full_title
            if hasattr(full_track, "full_title") and full_track.full_title:
                new_title = full_track.full_title
            # Priority 2: construct from title + version
            elif hasattr(full_track, "version") and full_track.version:
                new_title = f"{track_dict.get('title', '')} ({full_track.version})"
            
            # Update the track dict with enriched title
            track_dict = {**track_dict, "title": new_title}
        except Exception as e:
            logger.warning(f"Failed to enrich track {track_id}: {e}")
            # Keep original title on failure
        
        enriched.append(track_dict)
    
    return enriched + remainder
```

- [ ] **Step 2: Add unit tests for `enrich_tracks()`**

Add to `backend/tests/test_search.py`:
```python
from unittest.mock import Mock, MagicMock
from backend.search import enrich_tracks


def test_enrich_tracks_adds_version_to_title():
    # Mock tidalapi session and track
    mock_track = Mock()
    mock_track.full_title = None
    mock_track.version = "&ME Remix"
    
    mock_session = Mock()
    mock_session.track = Mock(return_value=mock_track)
    
    tracks = [{"id": 123, "title": "What To Do", "artist": "Artist"}]
    enriched = enrich_tracks(mock_session, tracks, top_n=5)
    
    assert enriched[0]["title"] == "What To Do (&ME Remix)"


def test_enrich_tracks_uses_full_title_when_available():
    mock_track = Mock()
    mock_track.full_title = "What To Do (&ME Remix)"
    
    mock_session = Mock()
    mock_session.track = Mock(return_value=mock_track)
    
    tracks = [{"id": 123, "title": "What To Do", "artist": "Artist"}]
    enriched = enrich_tracks(mock_session, tracks, top_n=5)
    
    assert enriched[0]["title"] == "What To Do (&ME Remix)"


def test_enrich_tracks_silent_fallback_on_error():
    mock_session = Mock()
    mock_session.track = Mock(side_effect=Exception("API error"))
    
    tracks = [{"id": 123, "title": "Original Title", "artist": "Artist"}]
    enriched = enrich_tracks(mock_session, tracks, top_n=5)
    
    # Should keep original title on failure
    assert enriched[0]["title"] == "Original Title"


def test_enrich_tracks_only_enrichs_top_n():
    mock_track = Mock()
    mock_track.full_title = "Enriched"
    
    mock_session = Mock()
    mock_session.track = Mock(return_value=mock_track)
    
    tracks = [
        {"id": 1, "title": "Track 1"},
        {"id": 2, "title": "Track 2"},
        {"id": 3, "title": "Track 3"},
    ]
    enriched = enrich_tracks(mock_session, tracks, top_n=2)
    
    # First 2 should be enriched (mock returns "Enriched")
    assert enriched[0]["title"] == "Enriched"
    assert enriched[1]["title"] == "Enriched"
    # Third should remain unchanged (not enriched due to top_n=2)
    assert enriched[2]["title"] == "Track 3"
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
python3 -m pytest backend/tests/test_search.py::test_enrich_tracks_adds_version_to_title -v
python3 -m pytest backend/tests/test_search.py::test_enrich_tracks_uses_full_title_when_available -v
python3 -m pytest backend/tests/test_search.py::test_enrich_tracks_silent_fallback_on_error -v
python3 -m pytest backend/tests/test_search.py::test_enrich_tracks_only_enrichs_top_n -v
```

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add backend/search.py backend/tests/test_search.py
git commit -m "feat: add metadata enrichment for top N search results"
```

---

### Task 3: Update `/search` Endpoint to Use Scoring + Enrichment

**Files:**
- Modify: `backend/main.py:107-118`
- Test: Manual testing via browser or curl

**Interfaces:**
- Consumes: `score_results()` and `enrich_tracks()` from Task 1 and Task 2
- Produces: Modified `/search` endpoint behavior (same API shape, better results)

- [ ] **Step 1: Import new functions in `backend/main.py`**

Verify imports at top of file include:
```python
from backend.search import search_tidal, get_album_tracks, get_playlist_tracks, resolve_url, score_results, enrich_tracks
```

- [ ] **Step 2: Update `/search` endpoint**

Replace the existing endpoint implementation (lines ~107-118):
```python
@app.get("/search")
async def search(q: str, type: str = "track"):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    models = [type] if type in ("track", "album", "playlist") else ["track", "album", "playlist"]
    artist_filter = None
    if " - " in q and type == "track":
        parts = q.split(" - ", 1)
        q = parts[0]
        artist_filter = parts[1]
    
    # Get raw search results
    raw = await asyncio.to_thread(search_tidal, auth_manager.session, q, models, artist_filter=artist_filter)
    
    # Score and sort tracks
    if raw.get("tracks"):
        scored = score_results(raw["tracks"], q, artist_filter)
        raw["tracks"] = [t for t, _ in scored]  # Strip scores
    
    # Enrich top 5 titles with full metadata
    if raw.get("tracks"):
        raw["tracks"] = await asyncio.to_thread(enrich_tracks, auth_manager.session, raw["tracks"], 5)
    
    return raw
```

- [ ] **Step 3: Verify no TypeScript/frontend changes needed**

The API response shape is unchanged — still returns `{tracks: [...], albums: [...], playlists: [...]}`. No frontend modification required.

- [ ] **Step 4: Manual test the endpoint**

```bash
# Start backend if not running
cd /Users/felipecanas/Projects/TidalExtractor
python3 -m uvicorn backend.main:app --reload --port 8000
```

Then test in browser at `http://localhost:3000` (frontend) or via curl:
```bash
curl "http://localhost:8000/search?q=What%20To%20Do%20-%20%26ME&type=track" \
  -H "Cookie: session=YOUR_SESSION_COOKIE"
```

Verify:
- Results are sorted with exact matches first
- Top 5 results have complete titles (e.g., `"What To Do (&ME Remix)"`)

- [ ] **Step 5: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add backend/main.py
git commit -m "feat: integrate scoring and enrichment into /search endpoint"
```

---

### Task 4: Run Full Test Suite and Verify Build

**Files:**
- All modified test files

- [ ] **Step 1: Run full backend test suite**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
python3 -m pytest backend/tests/ -v
```

Expected: All tests PASS

- [ ] **Step 2: Verify TypeScript build still works**

```bash
cd /Users/felipecanas/Projects/TidalExtractor/frontend
npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 3: Manual end-to-end test**

1. Start backend: `python3 -m uvicorn backend.main:app --reload --port 8000`
2. Start frontend: `npm run dev`
3. Open `http://localhost:3000`
4. Search for a known new release
5. Verify:
   - Correct track appears in top 3
   - Remix/version info displays in title
   - No console errors

- [ ] **Step 4: Commit final state**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add -A
git commit -m "chore: complete search improvements with scoring and enrichment"
```

---

## Success Criteria Checklist

After completing all tasks, verify:

- [ ] Correct track appears in **top 3** for exact searches
- [ ] Remix/version info visible in enriched tracks
- [ ] Search latency increase is acceptable (<500ms)
- [ ] All tests pass
- [ ] No user-facing errors from enrichment failures

---

## Rollback Plan

If issues arise, revert the last 3 commits:
```bash
cd /Users/felipecanas/Projects/TidalExtractor
git log --oneline -5  # Find the 3 search-related commits
git revert HEAD~2..HEAD  # Revert them
```

The app will return to previous search behavior (no scoring/enrichment).