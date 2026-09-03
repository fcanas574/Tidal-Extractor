import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from backend.key_detection import detect_key, file_hash, CAMELOT_MAP


def test_camelot_map_completeness():
    assert len(CAMELOT_MAP) == 24
    for i in range(1, 13):
        assert f"{i}A" in CAMELOT_MAP.values()
        assert f"{i}B" in CAMELOT_MAP.values()


def test_detect_key_mocked():
    with patch("backend.key_detection.librosa") as mock_librosa:
        sr = 22050
        duration = 5
        mock_y = np.random.randn(sr * duration).astype(np.float32)
        mock_librosa.load.return_value = (mock_y, sr)
        mock_chroma = np.zeros((12, 100))
        mock_chroma[0, :] = 1.0
        mock_librosa.feature.chroma_cqt.return_value = mock_chroma
        mock_librosa.beat.beat_track.return_value = (120.0, None)

        result = detect_key("/fake/path.flac")

        assert "camelot" in result
        assert "key" in result
        assert "confidence" in result
        assert len(result["camelot"]) == 2


def test_file_hash(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("hello world")
    h1 = file_hash(str(p))
    h2 = file_hash(str(p))
    assert h1 == h2
    assert len(h1) == 16
