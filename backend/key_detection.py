"""Musical key detection using chroma features and Camelot Wheel mapping."""
import os
import hashlib
import librosa
import numpy as np

# Camelot Wheel: maps (key, mode) -> camelot code
# Minor keys: 1A-12A, Major keys: 1B-12B
CAMELOT_MAP = {
    # Minor keys (A)
    "Ab minor": "1A", "Eb minor": "2A", "Bb minor": "3A",
    "F minor": "4A", "C minor": "5A", "G minor": "6A",
    "D minor": "7A", "A minor": "8A", "E minor": "9A",
    "B minor": "10A", "F# minor": "11A", "Db minor": "12A",
    # Major keys (B)
    "Ab major": "1B", "Eb major": "2B", "Bb major": "3B",
    "F major": "4B", "C major": "5B", "G major": "6B",
    "D major": "7B", "A major": "8B", "E major": "9B",
    "B major": "10B", "F# major": "11B", "Db major": "12B",
}

# Reverse: pitch class (0=C, 1=C#, ...) to note name
PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler key profiles (normalized)
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _key_to_pitch_class(key_name: str) -> int:
    """Convert a note name to pitch class (0-11)."""
    key_name = key_name.replace("b", "b").replace("Db", "C#").replace("Eb", "D#").replace("Gb", "F#").replace("Ab", "G#").replace("Bb", "A#")
    return PITCH_NAMES.index(key_name)


def _estimate_key(chroma: np.ndarray, tempo: float) -> tuple[str, str, float]:
    """Estimate key from chroma features. Returns (key, mode, confidence)."""
    chroma_avg = np.mean(chroma, axis=1)
    major_scores = []
    minor_scores = []

    for shift in range(12):
        shifted = np.roll(chroma_avg, shift)
        major_scores.append(np.correlate(shifted, MAJOR_PROFILE)[0])
        minor_scores.append(np.correlate(shifted, MINOR_PROFILE)[0])

    best_major = max(major_scores)
    best_major_idx = major_scores.index(best_major)

    best_minor = max(minor_scores)
    best_minor_idx = minor_scores.index(best_minor)

    if best_major > best_minor:
        key_name = PITCH_NAMES[best_major_idx]
        mode = "major"
        confidence = best_major / (best_major + best_minor)
    else:
        key_name = PITCH_NAMES[best_minor_idx]
        mode = "minor"
        confidence = best_minor / (best_major + best_minor)

    return f"{key_name} {mode}", mode, confidence


def detect_key(audio_path: str, sample_rate: int = 22050) -> dict:
    """Detect musical key from audio file and return Camelot notation.

    Returns: {"key": "Am", "camelot": "1A", "confidence": 0.87}
    """
    y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=512)
    key_full, mode, confidence = _estimate_key(chroma, 120.0)

    camelot = CAMELOT_MAP.get(key_full, None)
    if not camelot:
        pitch_class = PITCH_NAMES.index(key_full.split()[0])
        camelot = f"{(pitch_class % 12) + 1}{'A' if mode == 'minor' else 'B'}"

    return {
        "key": key_full.replace(" major", "").replace(" minor", "m"),
        "camelot": camelot,
        "confidence": round(float(confidence), 3),
    }


def file_hash(path: str) -> str:
    """Return MD5 hash of file content for cache lookup."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]
