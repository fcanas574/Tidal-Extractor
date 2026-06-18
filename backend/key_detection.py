"""Musical key detection using chroma features and Camelot Wheel mapping."""
import hashlib

import librosa
import numpy as np

# Camelot Wheel: maps (key, mode) -> camelot code
CAMELOT_MAP = {
    "Ab minor": "1A", "Eb minor": "2A", "Bb minor": "3A",
    "F minor": "4A", "C minor": "5A", "G minor": "6A",
    "D minor": "7A", "A minor": "8A", "E minor": "9A",
    "B minor": "10A", "F# minor": "11A", "Db minor": "12A",
    "Ab major": "1B", "Eb major": "2B", "Bb major": "3B",
    "F major": "4B", "C major": "5B", "G major": "6B",
    "D major": "7B", "A major": "8B", "E major": "9B",
    "B major": "10B", "F# major": "11B", "Db major": "12B",
}

_CAMELOT_NUMBERS = [5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10]
PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Temperley key profiles (pop/rock optimized)
MAJOR_PROFILE = np.array([5.61, 1.72, 3.67, 1.97, 4.99, 3.99, 1.79, 5.21, 2.30, 3.50, 2.06, 3.17])
MINOR_PROFILE = np.array([5.79, 1.73, 3.97, 4.42, 1.76, 3.63, 1.98, 5.01, 3.82, 2.07, 3.51, 2.08])


def _estimate_key(chroma: np.ndarray) -> tuple[str, str, float]:
    """Estimate key from chroma features using Temperley profiles."""
    chroma_avg = np.mean(chroma, axis=1)
    chroma_avg = chroma_avg / (np.sum(chroma_avg) + 1e-10)  # normalize

    major_scores = []
    minor_scores = []

    for shift in range(12):
        shifted = np.roll(chroma_avg, shift)
        major_scores.append(np.dot(shifted, MAJOR_PROFILE))
        minor_scores.append(np.dot(shifted, MINOR_PROFILE))

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
    """Detect musical key from audio file and return Camelot notation."""
    y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
    # Use CQT chroma for better pitch resolution
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    key_full, mode, confidence = _estimate_key(chroma)

    camelot = CAMELOT_MAP.get(key_full, None)
    if not camelot:
        pitch_class = PITCH_NAMES.index(key_full.split()[0])
        camelot = f"{_CAMELOT_NUMBERS[pitch_class]}{'A' if mode == 'minor' else 'B'}"

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
