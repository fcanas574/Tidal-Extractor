import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
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
        "artist_id": getattr(track.artist, "id", None) if track.artist else None,
        "album": track.album.name if track.album else "Unknown",
        "album_id": track.album.id if track.album else None,
        "duration": track.duration or 0,
        "quality": track.audio_quality or "UNKNOWN",
        "explicit": track.explicit or False,
        "isrc": track.isrc or None,
        "url": track.listen_url or "",
        "cover_url": cover_url,
        # DJ metadata from Tidal API
        "bpm": track.bpm,
        "key": track.key,
        "key_scale": track.key_scale,
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
    release_date = _release_date(album)
    release_type = getattr(album, "type", None)
    if not isinstance(release_type, str):
        release_type = None
    return {
        "id": album.id,
        "name": album.name or "Unknown",
        "artist": album.artist.name if album.artist else "Unknown",
        "artist_id": getattr(album.artist, "id", None) if album.artist else None,
        "num_tracks": album.num_tracks or 0,
        "release_date": release_date.isoformat() if release_date else None,
        "release_type": release_type,
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


def _release_date(album) -> Optional[date]:
    """Return the best available release date for an album-like object."""
    for attribute in ("available_release_date", "release_date", "tidal_release_date"):
        value = getattr(album, attribute, None)
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                continue
    return None


def _is_artist_release(album) -> bool:
    """Keep artist releases while excluding compilations and other collections."""
    release_type = getattr(album, "type", None)
    if not isinstance(release_type, str):
        return True
    return release_type.upper() in {"ALBUM", "EP", "SINGLE"}


def _unique_media(items):
    """Preserve media order while removing duplicate TIDAL objects by id."""
    seen = set()
    unique = []
    for item in items:
        item_id = getattr(item, "id", None)
        key = ("id", item_id) if item_id is not None else ("object", id(item))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _get_artist_releases(artist, artist_id: int):
    artist_releases = []
    release_errors = []
    try:
        artist_releases.extend(artist.get_albums())
    except Exception as exc:
        logger.warning("Failed to load albums for artist %s: %s", artist_id, exc)
        release_errors.append(f"Albums: {exc}")
    try:
        artist_releases.extend(artist.get_ep_singles())
    except Exception as exc:
        logger.warning("Failed to load EPs and singles for artist %s: %s", artist_id, exc)
        release_errors.append(f"EPs and singles: {exc}")

    artist_releases = _unique_media(
        album for album in artist_releases if _is_artist_release(album)
    )
    artist_releases.sort(
        key=lambda album: (
            _release_date(album) is not None,
            _release_date(album) or date.min,
        ),
        reverse=True,
    )
    return artist_releases, release_errors


def _load_artist_tracks(artist_releases, artist_id: int):
    track_errors = []
    all_tracks = []
    if artist_releases:
        with ThreadPoolExecutor(max_workers=min(8, len(artist_releases))) as executor:
            track_futures = [
                (album, executor.submit(album.tracks)) for album in artist_releases
            ]
            for album, future in track_futures:
                try:
                    all_tracks.extend(future.result())
                except Exception as exc:
                    logger.warning(
                        "Failed to load tracks for album %s on artist %s: %s",
                        getattr(album, "id", "unknown"),
                        artist_id,
                        exc,
                    )
                    track_errors.append(f"{getattr(album, 'name', 'Release')}: {exc}")
    return [format_track(track) for track in _unique_media(all_tracks)], track_errors


def _format_artist_summary(artist, artist_id: int) -> tuple[dict, list]:
    result = {
        "artist": format_artist(artist),
        "top_tracks": [],
        "tracks": [],
        "albums": [],
    }
    errors = {}

    try:
        result["top_tracks"] = [
            format_track(track) for track in artist.get_top_tracks(limit=5)
        ][:5]
    except Exception as exc:
        logger.warning("Failed to load top tracks for artist %s: %s", artist_id, exc)
        errors["top_tracks"] = str(exc)

    artist_releases, release_errors = _get_artist_releases(artist, artist_id)
    result["albums"] = [format_album(album) for album in artist_releases[:8]]
    if release_errors:
        errors["albums"] = " ".join(release_errors)

    if errors:
        result["errors"] = errors
    return result, artist_releases


def get_artist_summary(session: tidalapi.Session, artist_id: int) -> dict:
    """Load the fast artist overview without fetching every album's tracks."""
    artist = session.artist(artist_id)
    result, _ = _format_artist_summary(artist, artist_id)
    return result


def get_artist_tracks(session: tidalapi.Session, artist_id: int) -> dict:
    """Load the artist's full track catalog independently from the overview."""
    artist = session.artist(artist_id)
    artist_releases, release_errors = _get_artist_releases(artist, artist_id)
    tracks, track_errors = _load_artist_tracks(artist_releases, artist_id)
    result = {"tracks": tracks}
    errors = {}
    if release_errors:
        errors["albums"] = " ".join(release_errors)
    if track_errors:
        errors["tracks"] = " ".join(track_errors)
    if errors:
        result["errors"] = errors
    return result


def get_artist_details(session: tidalapi.Session, artist_id: int) -> dict:
    """Load the complete artist page for existing full-detail consumers."""
    artist = session.artist(artist_id)
    result, artist_releases = _format_artist_summary(artist, artist_id)
    tracks, track_errors = _load_artist_tracks(artist_releases, artist_id)
    result["tracks"] = tracks
    if track_errors:
        result.setdefault("errors", {})["tracks"] = " ".join(track_errors)
    return result


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
        details = get_artist_details(session, int(content_id))
        return {**empty, **details}

    return empty


def search_tidal(
    session: tidalapi.Session,
    query: str,
    models: Optional[List[str]] = None,
    limit: int = 50,
    offset: int = 0,
    artist_filter: Optional[str] = None,
) -> dict:
    if models is None:
        models = ["track", "artist", "album", "playlist"]

    model_map = {
        "track": tidalapi.Track,
        "artist": tidalapi.Artist,
        "album": tidalapi.Album,
        "playlist": tidalapi.Playlist,
    }
    tidal_models = [model_map[m] for m in models if m in model_map]

    if not tidal_models:
        return {"tracks": [], "artists": [], "albums": [], "playlists": []}

    results = session.search(query, models=tidal_models, limit=limit, offset=offset)

    tracks = [format_track(t) for t in results.get("tracks", [])]
    if artist_filter:
        artist_lower = artist_filter.lower()
        tracks = [t for t in tracks if artist_lower in t["artist"].lower()]
    artists = [format_artist(a) for a in results.get("artists", [])]
    albums = [format_album(a) for a in results.get("albums", [])]
    playlists = [format_playlist(p) for p in results.get("playlists", [])]

    return {"tracks": tracks, "artists": artists, "albums": albums, "playlists": playlists}


def _format_album_tracks(album) -> List[dict]:
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


def get_album_tracks(session: tidalapi.Session, album_id: int) -> List[dict]:
    return _format_album_tracks(session.album(album_id))


def get_album_details(session: tidalapi.Session, album_id: int) -> dict:
    album = session.album(album_id)
    return {"album": format_album(album), "tracks": _format_album_tracks(album)}


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
