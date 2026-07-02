# Backend: search.py

**Role:** Tidal search abstraction layer — query, album/playlist track listing, URL parsing/resolution, result scoring, and metadata enrichment. Pure functions wrapping `tidalapi`.

**See:** [[Search Subsystem]] · [[DJ Filters]]

## Formatters

### `format_track(track)` → dict
```python
{ id, title, artist, album, album_id, duration, quality, explicit, isrc, url,
  cover_url,                          # album.image(160)
  bpm, key, key_scale }               # DJ metadata from Tidal API
```
Cover art fetch is wrapped in try/except (some tracks lack album art).

### `format_album(album)` → dict
`{ id, name, artist, num_tracks, release_date, quality, cover_url }` (cover via `album.image(640)`)

### `format_playlist(playlist)` → dict
`{ id, name, num_tracks, creator, cover_url }` (cover via `playlist.image(640)`)

### `format_artist(artist)` → dict
`{ id, name, image_url, bio }` (image via `artist.image(480)`)

## Scoring: `score_results(tracks, query, artist_filter)` → `List[(track, score)]`

Relevance ranking applied after raw search:

| Signal | Points | Condition |
|--------|--------|-----------|
| Exact title match | +10 | `query_lower in title_lower` |
| Partial title match | +5 | any query word (>2 chars) in title |
| Recency | +5 | released within 30 days |
| Artist match | +10 | `artist_filter.lower() in artist.lower()` |

Sorted descending by score. This runs *before* DJ filters and pagination.

## Enrichment: `enrich_tracks(session, tracks, top_n=5)` → list

Improves titles for the **top N** tracks (the visible page):
1. `track.full_title` (if available) — preferred
2. `{title} ({version})` — constructed from version field (remixes, radio edits)
3. `title` — fallback (kept on any failure)

Failures are silent — logs a warning and keeps the original title. Only the first N are enriched to save API calls; the rest pass through unchanged.

## URL Parsing

### `TIDAL_URL_PATTERN` (regex)
```
https?://(?:listen\.)?tidal\.com/(?:browse/)?(track|album|playlist|artist)/([^\s/?]+)
```
Handles `tidal.com`, `listen.tidal.com`, and `/browse/` prefixed URLs.

### `parse_tidal_url(url)` → `(content_type, content_id)` or `None`
- Playlists have non-numeric IDs (UUIDs) — allowed
- Other types require numeric IDs (else `None`)

### `resolve_url(session, url)` → dict
Dispatches by type:
- **track** → `{tracks: [format_track(track)]}`
- **album** → `{albums: [format_album(album)]}`
- **playlist** → `{playlists: [format_playlist(playlist)]}`
- **artist** → `{artist, top_tracks[], albums[]}` (artist top tracks + discography)

Returns empty skeleton `{artist: None, top_tracks: [], tracks: [], albums: [], playlists: []}` merged with results.

## Core Search: `search_tidal(session, query, models, limit, artist_filter)` → dict

```python
model_map = { track: tidalapi.Track, album: tidalapi.Album, playlist: tidalapi.Playlist }
results = session.search(query, models=tidal_models, limit=limit)
tracks = [format_track(t) for t in results['tracks']]
if artist_filter:
    tracks = [t for t in tracks if artist_filter.lower() in t['artist'].lower()]
albums = ...; playlists = ...
return { tracks, albums, playlists }
```

`artist_filter` enables the "track - artist" search syntax (parsed in `main.py`).

## Collection Listing

### `get_album_tracks(session, album_id)` → list
`album.tracks()` formatted, each with `cover_url = album.image(640)`.

### `get_playlist_tracks(session, playlist_id)` → list
Same pattern for playlists.

## Notes

- All functions are **synchronous** (tidalapi is sync) — callers wrap in `asyncio.to_thread()`
- `format_track` is the single source of truth for track shape consumed by the frontend (`TrackResult` in `api.ts` mirrors it)
- The `bpm`/`key`/`key_scale` fields were added for [[DJ Filters]] — ~87% coverage on electronic music

## See Also

- [[Backend main]] (consumes this) · [[Frontend api]] (mirrors shapes)
