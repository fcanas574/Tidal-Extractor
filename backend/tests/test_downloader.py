import pytest
from unittest.mock import MagicMock
from backend.downloader import DownloadOrchestrator, extract_track_metadata
from backend.models import Database
from backend.config import AppConfig


@pytest.fixture
def orchestrator(tmp_path):
    import os
    db_path = str(tmp_path / "test.db")
    config_path = str(tmp_path / "config.yaml")
    output_dir = str(tmp_path / "downloads")
    os.makedirs(output_dir, exist_ok=True)
    db = Database(db_path)
    config = AppConfig(config_path)
    config.output_dir = output_dir
    config.save()
    return DownloadOrchestrator(db=db, config=config)


def test_build_filename_track(orchestrator):
    name = orchestrator._build_filename("Test Song", "Test Artist", ".flac")
    assert name == "Test Artist - Test Song.flac"


def test_build_filename_playlist_track(orchestrator):
    name = orchestrator._build_filename(
        "Track One", "Artist", ".flac",
        collection_name="My Playlist", track_num=1,
    )
    assert "My Playlist" in name
    assert "01 - Artist - Track One.flac" in name


def test_build_filename_album_track_no_collection(orchestrator):
    name = orchestrator._build_filename("Track Two", "Artist", ".flac")
    assert name == "Artist - Track Two.flac"


def test_sanitize_filename(orchestrator):
    assert orchestrator._sanitize_filename('Song: "Special" / Mix') == "Song - -Special - - Mix"
    assert orchestrator._sanitize_filename('Normal Song Name') == "Normal Song Name"
    assert orchestrator._sanitize_filename('Track/With\\Slashes') == "Track -With -Slashes"


def test_extract_track_metadata():
    mock_track = MagicMock()
    mock_track.title = "Test Song"
    mock_track.artist.name = "Test Artist"
    mock_track.artists = [MagicMock(name="Test Artist")]
    mock_track.album.name = "Test Album"
    mock_track.album.id = 999
    mock_track.track_num = 3
    mock_track.duration = 240
    mock_track.isrc = "US1234567890"
    mock_track.bpm = 128
    mock_track.key_scale = "Am"
    mock_track.key = "Am"
    mock_track.explicit = False
    mock_track.audio_quality = "LOSSLESS"

    meta = extract_track_metadata(mock_track)
    assert meta["title"] == "Test Song"
    assert meta["artist"] == "Test Artist"
    assert meta["album"] == "Test Album"
    assert meta["track_num"] == 3
    assert meta["isrc"] == "US1234567890"
    assert meta["bpm"] == 128
    assert meta["key"] == "Am"
