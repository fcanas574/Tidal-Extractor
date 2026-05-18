import subprocess
import pytest
import mutagen
from backend.tagger import tag_file


def _generate_test_flac(path: str):
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-c:a", "flac", "-y", path],
        capture_output=True, check=True,
    )


def _generate_test_mp3(path: str):
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-c:a", "libmp3lame", "-b:a", "320k", "-y", path],
        capture_output=True, check=True,
    )


@pytest.fixture
def test_flac(tmp_path):
    flac_path = str(tmp_path / "test.flac")
    _generate_test_flac(flac_path)
    return flac_path


@pytest.fixture
def test_mp3(tmp_path):
    mp3_path = str(tmp_path / "test.mp3")
    _generate_test_mp3(mp3_path)
    return mp3_path


METADATA = {
    "title": "Test Song",
    "artist": "Test Artist",
    "album": "Test Album",
    "track_num": 5,
    "genre": "Electronic",
    "year": "2024",
    "label": "Test Label",
    "isrc": "US1234567890",
    "bpm": 128,
    "key": "Am",
}


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_flac(test_flac):
    tag_file(test_flac, METADATA)
    f = mutagen.File(test_flac)
    assert f["title"][0] == "Test Song"
    assert f["artist"][0] == "Test Artist"
    assert f["album"][0] == "Test Album"
    assert f["tracknumber"][0] == "5"
    assert f["genre"][0] == "Electronic"
    assert f["date"][0] == "2024"
    assert f["label"][0] == "Test Label"
    assert f["isrc"][0] == "US1234567890"
    assert f["bpm"][0] == "128"
    assert f["initialkey"][0] == "Am"


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_mp3(test_mp3):
    tag_file(test_mp3, METADATA)
    f = mutagen.File(test_mp3)
    assert f["TIT2"][0] == "Test Song"
    assert f["TPE1"][0] == "Test Artist"
    assert f["TALB"][0] == "Test Album"
    assert f["TRCK"][0] == "5"
    assert f["TCON"][0] == "Electronic"
    assert str(f["TDRC"][0]) == "2024"
    assert f["TPUB"][0] == "Test Label"
    assert f["TSRC"][0] == "US1234567890"
    assert str(f["TBPM"][0]) == "128"
    assert f["TKEY"][0] == "Am"


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_with_cover_art(test_flac, tmp_path):
    cover_path = str(tmp_path / "cover.jpg")
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=1x1:d=0.01",
         "-frames:v", "1", "-y", cover_path],
        capture_output=True, check=True,
    )
    meta = {**METADATA, "cover_art_path": cover_path}
    tag_file(test_flac, meta)
    f = mutagen.File(test_flac)
    assert f.pictures, "Cover art should be embedded"


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_skips_none_values(test_flac):
    sparse_meta = {
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "track_num": None,
        "genre": None,
        "year": None,
        "label": None,
        "isrc": None,
        "bpm": 0,
        "key": None,
    }
    tag_file(test_flac, sparse_meta)
    f = mutagen.File(test_flac)
    assert f["title"][0] == "Test Song"
    assert "genre" not in f
    assert "bpm" not in f
    assert "initialkey" not in f
