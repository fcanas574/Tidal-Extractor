import pytest
from unittest.mock import MagicMock
from backend.search import search_tidal, format_track, format_album, format_playlist


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
