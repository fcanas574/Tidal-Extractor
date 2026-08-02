import os
import subprocess
import pytest
from unittest.mock import MagicMock, patch
from backend.downloader import DownloadOrchestrator, extract_track_metadata, _resolve_auto_quality
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


def test_resolve_auto_quality_hi_res():
    track = MagicMock(is_hi_res_lossless=True, is_lossless=True)
    assert _resolve_auto_quality(track) == "hi_res_lossless"


def test_resolve_auto_quality_lossless():
    track = MagicMock(is_hi_res_lossless=False, is_lossless=True)
    assert _resolve_auto_quality(track) == "high_lossless"


def test_resolve_auto_quality_lossy_only():
    track = MagicMock(is_hi_res_lossless=False, is_lossless=False)
    assert _resolve_auto_quality(track) == "low_320k"


@pytest.mark.asyncio
@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
async def test_download_track_removes_tmp_file_after_conversion(tmp_path):
    """A download that requires transcoding (source FLAC -> target MP3) must not
    leave the raw '.tmp' download behind once ffmpeg has produced the final file."""
    source_flac = tmp_path / "source.flac"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-c:a", "flac", "-y", str(source_flac)],
        capture_output=True, check=True,
    )
    flac_bytes = source_flac.read_bytes()

    output_dir = tmp_path / "downloads"
    output_dir.mkdir()
    db = Database(str(tmp_path / "test.db"))
    await db.init()
    config = AppConfig(str(tmp_path / "config.yaml"))
    config.output_dir = str(output_dir)

    orchestrator = DownloadOrchestrator(db=db, config=config)
    orchestrator.session = MagicMock()

    track = MagicMock()
    track.title = "Test Song"
    track.artist.name = "Test Artist"
    track.artists = []
    track.album.name = "Test Album"
    track.album.id = 1
    track.track_num = 1
    track.duration = 1
    track.isrc = None
    track.bpm = None
    track.key_scale = None
    track.key = None
    track.explicit = False
    track.audio_quality = "LOSSLESS"
    orchestrator.session.track.return_value = track
    orchestrator.session.album.side_effect = Exception("no cover")

    manifest = MagicMock()
    manifest.get_urls.return_value = ["http://fake/stream.flac"]
    manifest.file_extension = ".flac"
    stream = MagicMock()
    stream.get_stream_manifest.return_value = manifest
    track.get_stream.return_value = stream

    async def fake_aiter_bytes(chunk_size=65536):
        yield flac_bytes

    mock_resp = MagicMock()
    mock_resp.headers = {"content-length": str(len(flac_bytes))}
    mock_resp.aiter_bytes = fake_aiter_bytes

    class FakeStreamCtx:
        async def __aenter__(self):
            return mock_resp

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url):
            return FakeStreamCtx()

    queue_item = {
        "id": 1, "tidal_id": "123", "format": "MP3",
        "quality": "high_lossless", "item_type": "track",
        "from_collection": False,
    }

    with patch("httpx.AsyncClient", return_value=FakeClient()), \
         patch("backend.downloader.tag_file"), \
         patch("backend.downloader.tag_key"), \
         patch("backend.downloader._detect_key",
               return_value={"key": "C", "camelot": "8B", "confidence": 1.0}), \
         patch("backend.downloader.file_hash", return_value="hash"):
        final_path = await orchestrator.download_track(queue_item)

    assert os.path.exists(final_path)
    leftover_tmp = final_path + ".tmp"
    assert not os.path.exists(leftover_tmp), f"orphaned tmp file left behind: {leftover_tmp}"
