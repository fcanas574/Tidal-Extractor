import pytest
from unittest.mock import MagicMock
from backend.search import (
    search_tidal, format_track, format_album, format_playlist,
    parse_tidal_url, format_artist, resolve_url, score_results, enrich_tracks,
)


def test_format_track():
    mock_track = MagicMock()
    mock_track.id = 12345
    mock_track.title = "Test Song"
    mock_track.artist.name = "Test Artist"
    mock_track.album.name = "Test Album"
    mock_track.duration = 240
    mock_track.audio_quality = "LOSSLESS"
    mock_track.explicit = False
    mock_track.isrc = "US1234567890"
    mock_track.listen_url = "https://listen.tidal.com/album/99/track/12345"

    result = format_track(mock_track)
    assert result["id"] == 12345
    assert result["title"] == "Test Song"
    assert result["artist"] == "Test Artist"
    assert result["album"] == "Test Album"
    assert result["duration"] == 240
    assert result["quality"] == "LOSSLESS"


def test_format_album():
    mock_album = MagicMock()
    mock_album.id = 99
    mock_album.name = "Test Album"
    mock_album.artist.name = "Test Artist"
    mock_album.num_tracks = 12
    mock_album.release_date = "2024-01-01"
    mock_album.audio_quality = "LOSSLESS"
    mock_album.image = MagicMock(return_value="https://img.tidal.com/cover.jpg")

    result = format_album(mock_album)
    assert result["id"] == 99
    assert result["name"] == "Test Album"
    assert result["artist"] == "Test Artist"
    assert result["num_tracks"] == 12
    assert result["cover_url"] == "https://img.tidal.com/cover.jpg"


def test_format_playlist():
    mock_pl = MagicMock()
    mock_pl.id = "abc-123"
    mock_pl.name = "My Playlist"
    mock_pl.num_tracks = 50
    mock_pl.image = MagicMock(return_value="https://img.tidal.com/pl.jpg")

    result = format_playlist(mock_pl)
    assert result["id"] == "abc-123"
    assert result["name"] == "My Playlist"
    assert result["num_tracks"] == 50
    assert result["cover_url"] == "https://img.tidal.com/pl.jpg"


def test_search_tidal_tracks():
    mock_session = MagicMock()
    mock_track = MagicMock()
    mock_track.id = 1
    mock_track.title = "Found Song"
    mock_track.artist.name = "Found Artist"
    mock_track.album.name = "Found Album"
    mock_track.duration = 200
    mock_track.audio_quality = "LOSSLESS"
    mock_track.explicit = False
    mock_track.isrc = None
    mock_track.listen_url = ""

    mock_session.search.return_value = {"tracks": [mock_track], "albums": [], "playlists": [], "artists": [], "videos": [], "top_hit": None}

    results = search_tidal(mock_session, "Found Song", models=["track"])
    assert len(results["tracks"]) == 1
    assert results["tracks"][0]["title"] == "Found Song"


# --- parse_tidal_url tests ---

def test_parse_tidal_url_track():
    result = parse_tidal_url("https://tidal.com/browse/track/12345")
    assert result == ("track", "12345")

def test_parse_tidal_url_track_listen():
    result = parse_tidal_url("https://listen.tidal.com/track/12345")
    assert result == ("track", "12345")

def test_parse_tidal_url_album():
    result = parse_tidal_url("https://tidal.com/browse/album/999")
    assert result == ("album", "999")

def test_parse_tidal_url_playlist():
    result = parse_tidal_url("https://listen.tidal.com/playlist/abc-123")
    assert result == ("playlist", "abc-123")

def test_parse_tidal_url_artist():
    result = parse_tidal_url("https://tidal.com/browse/artist/42")
    assert result == ("artist", "42")

def test_parse_tidal_url_with_trailing_slug():
    result = parse_tidal_url("https://listen.tidal.com/track/12345/song-name")
    assert result == ("track", "12345")

def test_parse_tidal_url_invalid():
    result = parse_tidal_url("https://spotify.com/track/12345")
    assert result is None

def test_parse_tidal_url_malformed():
    result = parse_tidal_url("https://tidal.com/browse/notreal/abc")
    assert result is None


# --- format_artist / resolve_url tests ---

def test_format_artist():
    mock_artist = MagicMock()
    mock_artist.id = 42
    mock_artist.name = "Test Artist"
    mock_artist.image = MagicMock(return_value="https://img.tidal.com/artist.jpg")
    mock_artist.bio = "A test bio"
    result = format_artist(mock_artist)
    assert result["id"] == 42
    assert result["name"] == "Test Artist"
    assert result["image_url"] == "https://img.tidal.com/artist.jpg"
    assert result["bio"] == "A test bio"

def test_resolve_url_track():
    mock_session = MagicMock()
    mock_track = MagicMock()
    mock_track.id = 12345
    mock_track.title = "Test Song"
    mock_track.artist.name = "Test Artist"
    mock_track.album.name = "Test Album"
    mock_track.album.id = 99
    mock_track.duration = 240
    mock_track.audio_quality = "LOSSLESS"
    mock_track.explicit = False
    mock_track.isrc = None
    mock_track.listen_url = ""
    mock_session.track.return_value = mock_track

    result = resolve_url(mock_session, "https://listen.tidal.com/track/12345")
    assert len(result["tracks"]) == 1
    assert result["tracks"][0]["title"] == "Test Song"
    assert result["artist"] is None

def test_resolve_url_artist():
    mock_session = MagicMock()
    mock_artist_obj = MagicMock()
    mock_artist_obj.id = 42
    mock_artist_obj.name = "Test Artist"
    mock_artist_obj.image = MagicMock(return_value="https://img.tidal.com/artist.jpg")
    mock_artist_obj.bio = "A great artist"

    mock_top_track = MagicMock()
    mock_top_track.id = 1
    mock_top_track.title = "Top Hit"
    mock_top_track.artist.name = "Test Artist"
    mock_top_track.album.name = "Best Of"
    mock_top_track.album.id = 10
    mock_top_track.duration = 200
    mock_top_track.audio_quality = "LOSSLESS"
    mock_top_track.explicit = False
    mock_top_track.isrc = None
    mock_top_track.listen_url = ""
    mock_artist_obj.get_top_tracks.return_value = [mock_top_track]

    mock_album_obj = MagicMock()
    mock_album_obj.id = 99
    mock_album_obj.name = "Best Of"
    mock_album_obj.artist.name = "Test Artist"
    mock_album_obj.num_tracks = 12
    mock_album_obj.release_date = "2024-01-01"
    mock_album_obj.audio_quality = "LOSSLESS"
    mock_album_obj.image = MagicMock(return_value="https://img.tidal.com/album.jpg")
    mock_artist_obj.get_albums.return_value = [mock_album_obj]

    mock_session.artist.return_value = mock_artist_obj

    result = resolve_url(mock_session, "https://listen.tidal.com/artist/42")
    assert result["artist"]["name"] == "Test Artist"
    assert len(result["top_tracks"]) == 1
    assert result["top_tracks"][0]["title"] == "Top Hit"
    assert len(result["albums"]) == 1
    assert result["albums"][0]["name"] == "Best Of"

def test_resolve_url_invalid():
    mock_session = MagicMock()
    with pytest.raises(ValueError):
        resolve_url(mock_session, "https://spotify.com/track/12345")


# --- score_results tests ---

from datetime import date, timedelta


def test_score_results_exact_title_match():
    tracks = [
        {"title": "Abyss", "artist": "Orgyia", "release_date": None},
        {"title": "Different Song", "artist": "Other", "release_date": None},
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


# --- enrich_tracks tests ---

from unittest.mock import Mock


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
