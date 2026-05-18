import pytest
from backend.config import AppConfig


def test_load_defaults_when_file_missing(tmp_path):
    cfg = AppConfig(str(tmp_path / "nonexistent.yaml"))
    assert cfg.default_quality == "high_lossless"
    assert cfg.default_format == "FLAC"
    assert "TidalDownloads" in cfg.output_dir


def test_save_and_reload(tmp_path):
    cfg = AppConfig(str(tmp_path / "test_config.yaml"))
    cfg.default_quality = "low_320k"
    cfg.default_format = "MP3"
    cfg.output_dir = "/tmp/music"
    cfg.save()

    cfg2 = AppConfig(str(tmp_path / "test_config.yaml"))
    assert cfg2.default_quality == "low_320k"
    assert cfg2.default_format == "MP3"
    assert cfg2.output_dir == "/tmp/music"


def test_update_and_persist(tmp_path):
    cfg = AppConfig(str(tmp_path / "test_config.yaml"))
    cfg.update(default_format="M4A")
    cfg.save()

    cfg2 = AppConfig(str(tmp_path / "test_config.yaml"))
    assert cfg2.default_format == "M4A"
