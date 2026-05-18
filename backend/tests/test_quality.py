import subprocess
import pytest
from backend.quality import get_bitrate, bitrate_meets_threshold, QUALITY_PRESETS


def test_bitrate_meets_threshold_lossless():
    assert bitrate_meets_threshold("high_lossless", 1011) is True


def test_bitrate_meets_threshold_below_lossless():
    assert bitrate_meets_threshold("high_lossless", 200) is False


def test_bitrate_meets_threshold_320k():
    assert bitrate_meets_threshold("low_320k", 318) is True


def test_bitrate_meets_threshold_96k():
    assert bitrate_meets_threshold("low_96k", 95) is True


def test_quality_presets_order():
    assert list(QUALITY_PRESETS.keys()) == ["hi_res_lossless", "high_lossless", "low_320k", "low_96k"]


def test_get_bitrate_on_real_file():
    result = subprocess.run(["ffprobe", "-version"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("ffprobe not installed")

    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
        tmp_path = f.name
    try:
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", "1", "-c:a", "flac", "-y", tmp_path],
            capture_output=True, check=True,
        )
        bitrate = get_bitrate(tmp_path)
        assert bitrate is not None
        assert bitrate > 0
    finally:
        os.unlink(tmp_path)
