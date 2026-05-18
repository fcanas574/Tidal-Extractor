import os
import subprocess
import json
import pytest
from backend.converter import convert_format


@pytest.fixture
def test_flac(tmp_path):
    flac_path = str(tmp_path / "test.flac")
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-c:a", "flac", "-y", flac_path],
        capture_output=True, check=True,
    )
    return flac_path


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_convert_flac_to_mp3(test_flac, tmp_path):
    output = str(tmp_path / "test.mp3")
    result = convert_format(test_flac, output, "mp3", bitrate="320k")
    assert result == output
    assert os.path.exists(output)
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", output],
        capture_output=True, text=True,
    )
    data = json.loads(probe.stdout)
    assert data["streams"][0]["codec_name"] == "mp3"


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_convert_flac_to_m4a(test_flac, tmp_path):
    output = str(tmp_path / "test.m4a")
    result = convert_format(test_flac, output, "m4a", bitrate="320k")
    assert result == output
    assert os.path.exists(output)
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", output],
        capture_output=True, text=True,
    )
    data = json.loads(probe.stdout)
    assert data["streams"][0]["codec_name"] == "aac"


def test_convert_same_format_returns_original(test_flac):
    result = convert_format(test_flac, test_flac, "flac")
    assert result == test_flac
