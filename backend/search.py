import logging
import re
from datetime import date, timedelta
from typing import List, Optional, Tuple

import tidalapi

logger = logging.getLogger(__name__)


def format_track(track) -> dict:
    cover_url = None
    if track.album:
        try:
            cover_url = track.album.image(160)
        except Exception:
            pass
    return {
        "id": track.id,
        "title": track.title or "Unknown",
        "artist": track.artist.name if track.artist else "Unknown",
        "album": track.album.name if track.album else "Unknown",
        "album_id": track.album.id if track.album else None,
        "duration": track.duration or 0,
        "quality": track.audio_quality or "UNKNOWN",
        "explicit": track.explicit or False,
        "isrc": track.isrc or None,
        "url": track.listen_url or "",
        "cover_url": cover_url,
    }


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


def enrich_tracks(session, tracks: List[dict], top_n: int = 5) -> List[dict]:
    """
    Enrich top N tracks with full metadata (version/remix info).

    For each track, fetch the full Track object and construct complete title:
    1. track.full_title (if available)
    2. track.title + " (" + track.version + ")" (if version exists)
    3. track.title (fallback)

    Failures are silent — log warning and keep original title.
    """
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


def format_album(album) -> dict:
    cover_url = None
    try:
        cover_url = album.image(640)
    except Exception:
        pass
    return {
        "id": album.id,
        "name": album.name or "Unknown",
        "artist": album.artist.name if album.artist else "Unknown",
        "num_tracks": album.num_tracks or 0,
        "release_date": str(album.release_date) if album.release_date else None,
        "quality": album.audio_quality if hasattr(album, "audio_quality") else "UNKNOWN",
        "cover_url": cover_url,
    }


def format_playlist(playlist) -> dict:
    cover_url = None
    try:
        cover_url = playlist.image(640)
    except Exception:
        pass
    return {
        "id": playlist.id,
        "name": playlist.name or "Unknown",
        "num_tracks": playlist.num_tracks or 0,
        "creator": playlist.creator.name if hasattr(playlist, "creator") and playlist.creator else None,
        "cover_url": cover_url,
    }


TIDAL_URL_PATTERN = re.compile(
    r"https?://(?:listen\.)?tidal\.com/(?:browse/)?(track|album|playlist|artist)/([^\s/?]+)"
)


def parse_tidal_url(url: str) -> Optional[Tuple[str, str]]:
    match = TIDAL_URL_PATTERN.match(url.strip())
    if not match:
        return None
    content_type = match.group(1)
    content_id = match.group(2)
    if content_type != "playlist" and not content_id.isdigit():
        return None
    return (content_type, content_id)


def format_artist(artist) -> dict:
    image_url = None
    try:
        image_url = artist.image(480)
    except Exception:
        pass
    return {
        "id": artist.id,
        "name": artist.name or "Unknown",
        "image_url": image_url,
        "bio": getattr(artist, "bio", None),
    }


def resolve_url(session: tidalapi.Session, url: str) -> dict:
    parsed = parse_tidal_url(url)
    if parsed is None:
        raise ValueError(f"Cannot parse Tidal URL: {url}")

    content_type, content_id = parsed
    empty = {"artist": None, "top_tracks": [], "tracks": [], "albums": [], "playlists": []}

    if content_type == "track":
        track = session.track(int(content_id))
        return {**empty, "tracks": [format_track(track)]}

    if content_type == "album":
        album = session.album(int(content_id))
        return {**empty, "albums": [format_album(album)]}

    if content_type == "playlist":
        playlist = session.playlist(content_id)
        return {**empty, "playlists": [format_playlist(playlist)]}

    if content_type == "artist":
        artist = session.artist(int(content_id))
        top_tracks = [format_track(t) for t in artist.get_top_tracks()]
        albums = [format_album(a) for a in artist.get_albums()]
        return {**empty, "artist": format_artist(artist), "top_tracks": top_tracks, "albums": albums}

    return empty


def search_tidal(session: tidalapi.Session, query: str, models: Optional[List[str]] = None, limit: int = 50, artist_filter: Optional[str] = None) -> dict:
    if models is None:
        models = ["track", "album", "playlist"]

    model_map = {
        "track": tidalapi.Track,
        "album": tidalapi.Album,
        "playlist": tidalapi.Playlist,
    }
    tidal_models = [model_map[m] for m in models if m in model_map]

    if not tidal_models:
        return {"tracks": [], "albums": [], "playlists": []}

    results = session.search(query, models=tidal_models, limit=limit)

    tracks = [format_track(t) for t in results.get("tracks", [])]
    if artist_filter:
        artist_lower = artist_filter.lower()
        tracks = [t for t in tracks if artist_lower in t["artist"].lower()]
    albums = [format_album(a) for a in results.get("albums", [])]
    playlists = [format_playlist(p) for p in results.get("playlists", [])]

    return {"tracks": tracks, "albums": albums, "playlists": playlists}


def get_album_tracks(session: tidalapi.Session, album_id: int) -> List[dict]:
    album = session.album(album_id)
    tracks = album.tracks()
    result = []
    for t in tracks:
        formatted = format_track(t)
        try:
            formatted["cover_url"] = album.image(640)
        except Exception:
            pass
        result.append(formatted)
    return result


def get_playlist_tracks(session: tidalapi.Session, playlist_id: str) -> List[dict]:
    playlist = session.playlist(playlist_id)
    tracks = playlist.tracks()
    result = []
    for t in tracks:
        formatted = format_track(t)
        try:
            formatted["cover_url"] = playlist.image(640)
        except Exception:
            pass
        result.append(formatted)
    return result
