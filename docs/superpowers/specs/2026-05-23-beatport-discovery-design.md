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
2. **Load tracks** — `GET /beatport/tracks/{genre_id}` returns Top 10 with cover art, artist, title, BPM, key, ISRC, and Beatport URL.
3. **Preview** — User clicks preview → `GET /beatport/preview/{track_id}` returns `stream_url` → hidden `<audio>` element plays it. Button toggles play/pause. Only one preview plays at a time.
4. **Download** — User clicks download → `POST /beatport/match` searches Tidal by ISRC (most reliable), falls back to artist+title search → returns best Tidal match → adds to download queue with current quality/format settings.

## Beatport API Details

- **Internal API** (`api-internal.beatportprod.com/v4`) — genre lists and top tracks. Works server-side without user OAuth.
- **Public API** (`api.beatport.com/v4`) — OAuth 2.0 PKCE for authenticated endpoints (stream URLs, user library).
- **TrackStream** — separate API call per track, returns `stream_url`, `sample_start_ms`, `sample_end_ms`. The stream URL serves low-bitrate audio sufficient for preview.
- **Pagination** — all list endpoints support `page` and `per_page` (max 100).
- **Auth flow** — Username/password login via `/auth/login/` or OAuth 2.0 PKCE. Tokens cached to disk between restarts.

## Track Matching Strategy (Beatport → Tidal)

1. **ISRC lookup** — Search Tidal by track ISRC. If exact match found, use it. Most reliable.
2. **Artist + Title fallback** — If ISRC fails, search Tidal for `"{artist} {title}"`, pick best match by:
   - Exact artist name match preferred
   - Duration similarity as tiebreaker
3. **No match** — Download button disabled with "Not on Tidal" label.

## Beatport Auth

- Credentials stored in `config.yaml` as `beatport_username` / `beatport_password` (optional).
- If not configured, BeatportView shows a login form (username + password fields).
- Login calls `/auth/login/` on the public API, returns access + refresh tokens.
- Tokens cached in memory; refresh automatically before expiry.

## Frontend Components

### BeatportView.tsx (new)

States: loading, loaded, error, unauthenticated.

- **Genre selector** — horizontal scrollable pill bar or dropdown at top. Highlights active genre. Genres load once on mount.
- **Track list** — 10 glass cards matching existing SearchView/QueueView style. Each card shows:
  - Cover art (thumbnail, left-aligned)
  - Title (primary line)
  - Artist(s) (secondary line)
  - BPM · Key (metadata badges)
  - Preview button (play/pause toggle, compact)
  - Download button (or "Not on Tidal" if unmatchable)
- **Preview player** — hidden `<audio>` element. Clicking preview on a different track stops the current one. Button shows play icon when idle, pause icon when playing, spinner while loading stream URL.
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
Body: `{isrc, artist, title}`. Returns `{matched: true, tidal_track: {...}}` or `{matched: false}`. Tidal track format matches existing `TrackResult` interface so the frontend can reuse `queue.add()`.

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
- **Track not on Tidal** — Download button shows disabled "Not on Tidal" after match attempt.
- **Preview stream fails** — Show error toast, keep preview button enabled for retry.
- **Genre list empty** — Show "Unable to load genres" with retry button.
- **Slow stream URL fetch** — Preview button shows spinner while loading. Timeout after 10 seconds.
- **Multiple rapid preview clicks** — Abort in-flight stream URL request when new preview starts.
- **Beatport API rate limiting** — Genre list cached. Track lists cached for 5 minutes per genre.

## Testing

- Backend: Unit tests for `BeatportClient` auth flow, genre parsing, track parsing, stream URL parsing, Tidal matching logic. Mock Beatport HTTP responses.
- Frontend: Component tests for BeatportView loading/loaded/error/unauth states. Preview play/pause toggle. Download button states.
- Integration: End-to-end test of genre select → tracks load → preview plays → download queues.
