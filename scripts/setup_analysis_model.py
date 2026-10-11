"""Explicitly install Beat This!'s supported local checkpoint.

Importing this module never performs network or filesystem setup. Run it as a
CLI only when the optional local beat model is wanted.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.request
import zipfile


BEAT_THIS_VERSION = "1.1.0"
LIBROSA_VERSION = "0.11.0"
NUMPY_VERSION = "2.2.6"
SCIPY_VERSION = "1.15.3"
TORCH_VERSION = "2.9.1"
TORCHAUDIO_VERSION = "2.9.1"
SUPPORTED_MODELS = ("final0",)
MODEL_BASE_URL = "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp"
MODEL_URLS = {"final0": f"{MODEL_BASE_URL}/final0.ckpt"}
MANIFEST_TEMPLATE = "{model_id}.manifest.json"
_CHUNK_SIZE = 1024 * 1024
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _user_data_model_dir() -> Path:
    override = os.environ.get("TIDALEXTRACTOR_MODEL_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "darwin":
        data_root = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        data_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        data_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_root / "TidalExtractor" / "models"


MODEL_DIR = _user_data_model_dir()


def _require_supported_model(model_id: str) -> str:
    if model_id not in SUPPORTED_MODELS:
        raise ValueError(f"unsupported model {model_id!r}; choose final0")
    return model_id


def _installed_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"{distribution} is not installed; install requirements-analysis.txt first"
        ) from exc


def _validate_runtime() -> None:
    """Fail early unless the pinned inference package and Torch API are present."""
    expected = {
        "beat-this": BEAT_THIS_VERSION,
        "librosa": LIBROSA_VERSION,
        "numpy": NUMPY_VERSION,
        "scipy": SCIPY_VERSION,
        "torch": TORCH_VERSION,
        "torchaudio": TORCHAUDIO_VERSION,
    }
    installed = {name: _installed_version(name) for name in expected}
    mismatches = [
        f"{name}=={installed[name]} (expected {version})"
        for name, version in expected.items()
        if installed[name] != version
    ]
    if mismatches:
        raise RuntimeError(
            "incompatible local beat-analysis runtime: " + ", ".join(mismatches)
        )

    try:
        inference = importlib.import_module("beat_this.inference")
    except Exception as exc:
        raise RuntimeError("Beat This! inference API could not be imported") from exc
    if not callable(getattr(inference, "File2Beats", None)):
        raise RuntimeError("Beat This! 1.1.0 does not provide File2Beats")


def _checkpoint_path(model_id: str) -> Path:
    return MODEL_DIR / f"{model_id}.ckpt"


def _manifest_path(model_id: str) -> Path:
    return MODEL_DIR / MANIFEST_TEMPLATE.format(model_id=model_id)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as checkpoint:
        for chunk in iter(lambda: checkpoint.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_checkpoint_archive(path: Path) -> None:
    """Reject empty, truncated, or non-PyTorch-archive responses before use."""
    try:
        with zipfile.ZipFile(path) as archive:
            if not any(name.endswith("data.pkl") for name in archive.namelist()):
                raise ValueError("checkpoint archive has no PyTorch data.pkl entry")
            if archive.testzip() is not None:
                raise ValueError("checkpoint archive contains a corrupt member")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("download is not a valid PyTorch checkpoint archive") from exc


def _verified_local_model(model_id: str) -> Path:
    checkpoint = _checkpoint_path(model_id)
    manifest_path = _manifest_path(model_id)
    if not checkpoint.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(
            f"model {model_id} is not set up; run "
            "python scripts/setup_analysis_model.py --model final0"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid model manifest: {manifest_path}") from exc
    expected_fields = {
        "model_id": model_id,
        "filename": checkpoint.name,
        "source_url": MODEL_URLS[model_id],
    }
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != value for key, value in expected_fields.items()
    ):
        raise ValueError("model manifest does not match the expected model and source")

    expected_digest = manifest.get("sha256")
    if not isinstance(expected_digest, str) or not _HEX_SHA256.fullmatch(expected_digest):
        raise ValueError("model manifest has an invalid SHA-256")
    _validate_checkpoint_archive(checkpoint)
    actual_digest = _sha256_file(checkpoint)
    if actual_digest != expected_digest:
        raise ValueError("checkpoint SHA-256 does not match its manifest")
    return checkpoint


def get_model_path(model_id: str = "final0") -> Path:
    """Return a local model only after runtime and manifest integrity checks."""
    model_id = _require_supported_model(model_id)
    _validate_runtime()
    return _verified_local_model(model_id)


def _open_url(url: str):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "TidalExtractor optional beat-model setup"},
    )
    return urllib.request.urlopen(request, timeout=90)


def _write_manifest_atomically(path: Path, manifest: dict[str, str]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(manifest, temporary, sort_keys=True, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def provision_model(model_id: str = "final0") -> Path:
    """Download and verify the selected model, storing it outside the project."""
    model_id = _require_supported_model(model_id)
    _validate_runtime()

    checkpoint = _checkpoint_path(model_id)
    manifest_path = _manifest_path(model_id)
    if checkpoint.exists() or manifest_path.exists():
        return _verified_local_model(model_id)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    installed_checkpoint = False
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=MODEL_DIR,
            prefix=f".{model_id}.",
            suffix=".part",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            with _open_url(MODEL_URLS[model_id]) as response:
                digest = hashlib.sha256()
                total_bytes = 0
                while True:
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    temporary.write(chunk)
                    digest.update(chunk)
                    total_bytes += len(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())

        if total_bytes == 0:
            raise ValueError("downloaded checkpoint is empty")
        _validate_checkpoint_archive(temporary_path)
        actual_digest = _sha256_file(temporary_path)
        if actual_digest != digest.hexdigest():
            raise ValueError("downloaded checkpoint SHA-256 changed while being written")

        os.replace(temporary_path, checkpoint)
        temporary_path = None
        installed_checkpoint = True
        _write_manifest_atomically(
            manifest_path,
            {
                "model_id": model_id,
                "filename": checkpoint.name,
                "source_url": MODEL_URLS[model_id],
                "sha256": actual_digest,
            },
        )
        return _verified_local_model(model_id)
    except Exception:
        if installed_checkpoint:
            checkpoint.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _license_notice() -> str:
    return (
        "Notice: Beat This! 1.1.0 is MIT-licensed. The final0 checkpoint is an "
        "upstream model asset. The upstream README warns that some training files "
        "are copyrighted or distributed under limited Creative Commons licenses; "
        "review those terms before redistributing derived materials."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set up the optional local beat model.")
    parser.add_argument(
        "--model",
        choices=SUPPORTED_MODELS,
        required=True,
        help="upstream checkpoint to install (only final0 is currently supported)",
    )
    args = parser.parse_args(argv)
    print(_license_notice())
    try:
        model_path = provision_model(args.model)
    except Exception as exc:
        print(f"Model setup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Model ready: {model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
