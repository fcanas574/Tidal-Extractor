import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from io import BytesIO
import zipfile

import pytest

from scripts import setup_analysis_model as setup


CHECKPOINT_URL = (
    "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt"
)


@pytest.fixture(autouse=True)
def runtime_validator(monkeypatch):
    runtime_validator = setup._validate_runtime
    monkeypatch.setattr(setup, "_validate_runtime", lambda: None)
    return runtime_validator


def _checkpoint_bytes() -> bytes:
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("final0/data.pkl", b"test checkpoint")
        archive.writestr("final0/version", "3")
    return payload.getvalue()


def _write_local_model(model_dir: Path, contents: bytes, *, digest: str | None = None):
    model_dir.mkdir(parents=True)
    checkpoint = model_dir / "final0.ckpt"
    checkpoint.write_bytes(contents)
    manifest = {
        "model_id": "final0",
        "filename": checkpoint.name,
        "source_url": CHECKPOINT_URL,
        "sha256": digest or hashlib.sha256(contents).hexdigest(),
    }
    (model_dir / "final0.manifest.json").write_text(json.dumps(manifest))
    return checkpoint


def test_valid_checkpoint_is_reused_without_network(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    checkpoint = _write_local_model(model_dir, _checkpoint_bytes())
    monkeypatch.setattr(setup, "MODEL_DIR", model_dir)

    def unexpected_network(*_args, **_kwargs):
        raise AssertionError("a valid local checkpoint should be reused")

    monkeypatch.setattr(setup, "_open_url", unexpected_network)

    assert setup.get_model_path("final0") == checkpoint


def test_partial_checkpoint_download_is_removed(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    monkeypatch.setattr(setup, "MODEL_DIR", model_dir)
    requested_urls = []

    class InterruptedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            if not hasattr(self, "sent_partial"):
                self.sent_partial = True
                return b"partial"
            raise OSError("connection dropped")

    def fake_open_url(url):
        requested_urls.append(url)
        return InterruptedResponse()

    monkeypatch.setattr(setup, "_open_url", fake_open_url)

    with pytest.raises(OSError, match="connection dropped"):
        setup.provision_model("final0")

    assert requested_urls == [CHECKPOINT_URL]
    assert not model_dir.exists() or list(model_dir.iterdir()) == []


def test_manifest_mismatch_is_rejected(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    _write_local_model(model_dir, _checkpoint_bytes(), digest="0" * 64)
    monkeypatch.setattr(setup, "MODEL_DIR", model_dir)

    with pytest.raises(ValueError, match="SHA-256"):
        setup.get_model_path("final0")


def test_runtime_rejects_torch_version_mismatch(runtime_validator, monkeypatch):
    versions = {
        "beat-this": "1.1.0",
        "librosa": "0.11.0",
        "numpy": "2.2.6",
        "scipy": "1.15.3",
        "torch": "2.10.0",
        "torchaudio": "2.9.1",
    }
    monkeypatch.setattr(setup, "_installed_version", lambda name: versions[name])

    with pytest.raises(RuntimeError, match=r"torch==2\.10\.0 \(expected 2\.9\.1\)"):
        runtime_validator()


def test_invalid_checkpoint_download_is_removed(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    monkeypatch.setattr(setup, "MODEL_DIR", model_dir)
    requested_urls = []

    class InvalidResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            if not hasattr(self, "sent_data"):
                self.sent_data = True
                return b"not a checkpoint archive"
            return b""

    def fake_open_url(url):
        requested_urls.append(url)
        return InvalidResponse()

    monkeypatch.setattr(setup, "_open_url", fake_open_url)

    with pytest.raises(ValueError, match="checkpoint archive"):
        setup.provision_model("final0")

    assert requested_urls == [CHECKPOINT_URL]
    assert not model_dir.exists() or list(model_dir.iterdir()) == []


def test_app_import_never_downloads_model():
    project_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    existing_python_path = env.get("PYTHONPATH", "").split(os.pathsep)
    env["PYTHONPATH"] = os.pathsep.join(
        dict.fromkeys(filter(None, [*existing_python_path, str(project_root)]))
    )
    code = """
import urllib.request

def forbidden_network(*args, **kwargs):
    raise AssertionError("application import attempted a model download")

urllib.request.urlopen = forbidden_network
import backend.main
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
