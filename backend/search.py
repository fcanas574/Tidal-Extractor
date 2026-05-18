import logging
from typing import List, Optional

import tidalapi

logger = logging.getLogger(__name__)


def format_track(track) -> dict:
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
        "cover_url": None,
    }


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


def search_tidal(session: tidalapi.Session, query: str, models: Optional[List[str]] = None, limit: int = 20) -> dict:
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
