# Beatport Discovery Screen

## Overview

Add a "Beatport" tab to the navigation bar. Shows the Top 10 tracks for a selected genre. Each track has a preview button (plays low-quality stream from Beatport) and a download button (matches to Tidal via ISRC/artist+title, then adds to queue).

## Motivation

TidalExtractor currently only searches Tidal. Adding Beatport as a discovery layer gives users access to DJ-oriented charts and genre-specific top tracks. Beatport is the industry standard for electronic music discovery and its Top 10 per genre shows what's trending right now.

## Architecture

```
Frontend (React)                    Backend (FastAPI)
------------------                  ------------------
BeatportView.tsx (new)              beatport.py (new)
  ├─ Genre selector                   ├─ BeatportClient
  ├─ Track list (10 items)            │   ├─ OAuth 2.0 PKCE auth
  │   ├─ Cover art                    │   ├─ get_genres()
  │   ├─ Title / Artist / BPM / Key   │   ├─ get_top_tracks(genre_id)
  │   ├─ Preview button → <audio>     │   └─ get_stream_url(track_id)
  │   └─ Download button              ├─ track matching (ISRC → artist+title)
  └─ Hidden <audio> element           └─ REST endpoints in main.py

NavBar.tsx (edit)                   main.py (edit)
  └─ + "Beatport" tab               ├─ GET  /beatport/genres
                                    ├─ GET  /beatport/tracks/{genre_id}
                                    ├─ GET  /beatport/preview/{track_id}
                                    └─ POST /beatport/match (Beatport → Tidal)
```

## Data Flow

1. **Load genres** — On mount, `GET /beatport/genres` returns genre list (House, Techno, DnB, Trance, etc.). First genre auto-selected.
2. **Load tracks** — `GET /beatport/tracks/{genre_id}` returns Top 10 with cover art, artist, title, mix name, BPM, key, ISRC, duration, and Beatport URL.
3. **Preview** — User clicks preview → `GET /beatport/preview/{track_id}` returns `stream_url` → hidden `<audio>` element plays it. Button toggles play/pause. Only one preview plays at a time.
4. **Match** — User clicks download → `POST /beatport/match` runs the multi-layer matching pipeline (see below). Returns a list of Tidal candidates with confidence scores.
5. **Confirm** — If a single high-confidence match (≥95%), auto-queue it. If multiple candidates or medium confidence, show a confirmation dialog listing each candidate with title, artist, duration, quality, and a small preview button. User selects the correct one before queueing.

## Beatport API Details

- **Internal API** (`api-internal.beatportprod.com/v4`) — genre lists and top tracks. Works server-side without user OAuth.
- **Public API** (`api.beatport.com/v4`) — OAuth 2.0 PKCE for authenticated endpoints (stream URLs, user library).
- **TrackStream** — separate API call per track, returns `stream_url`, `sample_start_ms`, `sample_end_ms`. The stream URL serves low-bitrate audio sufficient for preview.
- **Pagination** — all list endpoints support `page` and `per_page` (max 100).
- **Auth flow** — Username/password login via `/auth/login/` or OAuth 2.0 PKCE. Tokens cached to disk between restarts.

## Track Matching Strategy (Beatport → Tidal)

Beatport tracks have rich metadata: `name` (title), `mix_name` (Extended Mix, Original Mix, Radio Edit, etc.), `artists`, `isrc`, `length_ms`, `bpm`, `key`, `release` (with label info). Tidal tracks have: `title`, `artist`, `album`, `duration`, `isrc`, `quality`. The matching pipeline uses all available fields to ensure precision.

### Layer 1: ISRC exact match

Search Tidal by ISRC. ISRC identifies a specific recording — same ISRC = same master. If one result, use it. If multiple (different releases of same ISRC), proceed to Layer 2 to pick the correct version.

### Layer 2: ISRC + version/mix matching

When ISRC returns multiple Tidal tracks, compare each candidate's title against the Beatport `mix_name`:
- Normalize mix names: "Extended Mix" ≈ "Extended" ≈ "Ext Mix" ≈ "Original Mix (Extended)"
- Normalize common patterns: "Radio Edit" ≈ "Radio Version" ≈ "Edit"
- If the Beatport track has no mix_name (empty/null), prefer the Tidal candidate whose title contains only the track name without any mix suffix
- Score each candidate by mix name similarity; top score wins

### Layer 3: Artist + Title + Mix search

If ISRC lookup returns nothing (ISRC missing or not on Tidal):
1. Build search query: `"{primary artist} {name} {mix_name}"` (e.g., "Jonas Blue Edge of Desire Extended Mix")
2. Search Tidal tracks with this query
3. From results, score each candidate:
   - Artist match (primary artist name appears in candidate artist): +40 points
   - Mix name present in candidate title: +30 points
   - Duration within ±5% of Beatport `length_ms`: +20 points
   - Duration within ±10%: +10 points
   - Remixer name present in candidate title or artist: +10 bonus

### Layer 4: Artist + Title search (no mix filter)

If Layer 3 returns no high-confidence matches:
1. Search Tidal for `"{primary artist} {name}"` (drop mix_name)
2. Return all candidates with scores. Show the user a confirmation dialog since we couldn't verify the exact version.

### Confidence thresholds

- **≥95 points** — Auto-match. Queue directly without confirmation.
- **50-94 points** — Medium confidence. Show confirmation dialog with top 3 candidates.
- **<50 points or no results** — Show "Not on Tidal" with an option to manually search.

### Label awareness

Some labels consistently do or don't put certain versions on Tidal. While we won't hardcode a label database, the scoring system naturally handles this:
- Labels that put extended mixes on Tidal (e.g., Defected) → mix_name matches in Layer 2/3 → high confidence → auto-match
- Labels that don't (e.g., TSZR) → mix_name won't appear in Tidal results → low score → user confirmation triggered or "Not on Tidal" shown

### Confirmation dialog

When confidence is medium (50-94 pts), show a modal/dialog:
- **Left side**: Beatport track info (title, artist, mix_name, duration, cover art)
- **Right side**: Tidal candidates list. Each candidate shows:
  - Title (with version/mix highlighted if different from Beatport)
  - Artist
  - Duration (with color: green if within ±5%, yellow if ±10%, red if >10% off)
  - Quality badge
  - Small preview button (plays Tidal 30s preview via existing Tidal track URL if available)
  - "Select" button
- User picks the correct match, which queues the download

## Beatport Auth

- Credentials stored in `config.yaml` as `beatport_username` / `beatport_password` (optional).
- If not configured, BeatportView shows a login form (username + password fields).
- Login calls `/auth/login/` on the public API, returns access + refresh tokens.
- Tokens cached in memory; refresh automatically before expiry.

## Frontend Components

### BeatportView.tsx (new)

States: loading, loaded, error, unauthenticated, matching (per-track), confirming (dialog).

- **Genre selector** — horizontal scrollable pill bar or dropdown at top. Highlights active genre. Genres load once on mount.
- **Track list** — 10 glass cards matching existing SearchView/QueueView style. Each card shows:
  - Cover art (thumbnail, left-aligned)
  - Title + mix name (primary line, e.g., "Edge of Desire (Extended Mix)")
  - Artist(s) (secondary line)
  - BPM · Key · Duration (metadata badges)
  - Preview button (play/pause toggle, compact)
  - Download button with states: "Download" (idle), spinner (matching), "Not on Tidal" (no match), "Select Version..." (medium confidence, opens confirmation dialog)
- **Preview player** — hidden `<audio>` element. Clicking preview on a different track stops the current one. Button shows play icon when idle, pause icon when playing, spinner while loading stream URL.
- **Confirmation dialog** — modal overlay when match confidence is medium (50-94 pts):
  - Header: "Confirm Match — {beatport track name}"
  - Left panel: Beatport track summary (cover, title, mix, artist, duration, BPM, key)
  - Right panel: Tidal candidates list (max 5). Each candidate card:
    - Title (mix/version differences highlighted)
    - Artist
    - Duration (color-coded: green ≤5% off, yellow ≤10%, red >10%)
    - Quality badge
    - "Select" button → queues download and closes dialog
  - "Cancel" button to close without downloading
- **Loading** — skeleton cards (3-4 placeholder cards)
- **Error** — error message with retry button
- **Unauthenticated** — login form (username, password, submit)

### NavBar.tsx (edit)

Add "Beatport" tab between "Search" and "Queue". Icon: note/headphones symbol. Existing tab pattern unchanged.

## Backend Endpoints

### `GET /beatport/genres`
Returns list of Beatport genres: `[{id, name, slug}]`. Cached for session lifetime (genres rarely change).

### `GET /beatport/tracks/{genre_id}`
Returns Top 10 tracks for genre: `[{id, name, artists, mix_name, bpm, key, genre, length, length_ms, isrc, cover_url, beatport_url}]`. Cover URL from release image at 320px.

### `GET /beatport/preview/{track_id}`
Returns `{stream_url}` for the track. Fetches `TrackStream` from Beatport API on demand. Stream URL is short-lived; frontend should play immediately.

### `POST /beatport/match`
Body: `{isrc, artist, name, mix_name, length_ms, remixers}` (all Beatport track fields used for matching).
Returns:
```json
{
  "confidence": 95,
  "auto_matched": true,
  "candidates": [
    {
      "score": 95,
      "tidal_track": { ...TrackResult },
      "match_details": {
        "isrc_match": true,
        "mix_match": true,
        "duration_match": "within_5pct",
        "artist_match": true
      }
    }
  ]
}
```
- `confidence` — top candidate score (0-100)
- `auto_matched` — true if confidence ≥95, frontend should auto-queue
- `candidates` — sorted by score descending, max 5 returned
- `match_details` — breakdown of what matched for transparency

## Files Changed/Created

| File | Action | Purpose |
|---|---|---|
| `backend/beatport.py` | New | Beatport API client (auth, genres, top tracks, stream, matching) |
| `backend/main.py` | Edit | 4 new REST endpoints for Beatport |
| `frontend/src/components/BeatportView.tsx` | New | Beatport discovery UI |
| `frontend/src/components/NavBar.tsx` | Edit | Add "Beatport" tab |
| `frontend/src/api.ts` | Edit | Beatport API types and functions |
| `config.yaml` | Edit | Optional Beatport credentials |

## Edge Cases

- **Beatport auth expired** — Backend detects 401, clears cached token, returns 401 to frontend. Frontend shows re-authenticate prompt.
- **Track not on Tidal** — Download button shows disabled "Not on Tidal" after match attempt. User can click to see why (no ISRC match, no artist+title match).
- **Multi-artist tracks** — Use the first/primary artist for Tidal search. All artists displayed in UI. Match scoring checks all artists against candidates.
- **Extended mix on Beatport but only Radio Edit on Tidal** — Layer 3 with mix matching catches this. Candidate with "Radio Edit" gets partial mix score (15 pts instead of 30). Duration likely won't match (±10% threshold). Confidence drops to medium → confirmation dialog shown so user can decide.
- **Label doesn't put extended mixes on streaming** — Beatport shows Extended Mix but Tidal only has Original/Radio. Mix_name mismatch in Layer 2/3 → lower score → user sees candidates and picks whichever version they want (or cancels).
- **Same track, different releases on Tidal** — ISRC returns multiple candidates. Layer 2 picks the one with matching mix_name. If none match, confirmation dialog shows all.
- **Preview stream fails** — Show error toast, keep preview button enabled for retry.
- **Genre list empty** — Show "Unable to load genres" with retry button.
- **Slow stream URL fetch** — Preview button shows spinner while loading. Timeout after 10 seconds.
- **Multiple rapid preview clicks** — Abort in-flight stream URL request when new preview starts.
- **Beatport API rate limiting** — Genre list cached. Track lists cached for 5 minutes per genre.

## Testing

- Backend: Unit tests for `BeatportClient` auth flow, genre parsing, track parsing, stream URL parsing, Tidal matching logic. Mock Beatport HTTP responses.
- Frontend: Component tests for BeatportView loading/loaded/error/unauth states. Preview play/pause toggle. Download button states.
- Integration: End-to-end test of genre select → tracks load → preview plays → download queues.
