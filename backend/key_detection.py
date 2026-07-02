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

# Reverse mapping: Tidal key name → Camelot number (derived from CAMELOT_MAP)
# Based on Circle of Fifths: Ab=1, Eb=2, Bb=3, F=4, C=5, G=6, D=7, A=8, E=9, B=10, F#=11, Db=12
PITCH_TO_CAMELOT_NUM = {
    'Ab': 1, 'GSharp': 1,
    'Eb': 2, 'DSharp': 2,
    'Bb': 3, 'ASharp': 3,
    'F': 4,
    'C': 5,
    'G': 6,
    'D': 7,
    'A': 8,
    'E': 9,
    'B': 10,
    'FSharp': 11, 'Gb': 11,
    'Db': 12, 'CSharp': 12,
}


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
    """Detect musical key and BPM from audio file and return Camelot notation."""
    y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
    # Use CQT chroma for better pitch resolution
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    key_full, mode, confidence = _estimate_key(chroma)

    camelot = CAMELOT_MAP.get(key_full, None)
    if not camelot:
        pitch_class = PITCH_NAMES.index(key_full.split()[0])
        camelot = f"{_CAMELOT_NUMBERS[pitch_class]}{'A' if mode == 'minor' else 'B'}"

    # Detect BPM using tempo estimation
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if hasattr(tempo, 'item') else float(tempo[0]) if isinstance(tempo, (list, tuple)) else float(tempo)

    return {
        "key": key_full.replace(" major", "").replace(" minor", "m"),
        "camelot": camelot,
        "bpm": round(bpm, 2),
        "confidence": round(float(confidence), 3),
    }


def file_hash(path: str) -> str:
    """Return MD5 hash of file content for cache lookup."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def convert_to_camelot(key: str, scale: str) -> str:
    """
    Convert Tidal key notation to Camelot notation.

    Args:
        key: Tidal key name (e.g., 'C', 'CSharp', 'Db', 'F')
        scale: 'MAJOR' or 'MINOR'

    Returns:
        Camelot notation (e.g., '5B', '5A')

    Examples:
        >>> convert_to_camelot('C', 'MAJOR')
        '5B'
        >>> convert_to_camelot('F', 'MINOR')
        '5A'
        >>> convert_to_camelot('GSharp', 'MAJOR')
        '1B'
    """
    key_normalized = key.strip()
    scale_upper = scale.upper() if scale else 'MAJOR'

    number = PITCH_TO_CAMELOT_NUM.get(key_normalized)
    if number is None:
        # Fallback: try common aliases
        aliases = {'C#': 6, 'D#': 8, 'F#': 11, 'G#': 1, 'A#': 3}
        number = aliases.get(key_normalized.replace('Sharp', '#').replace('Flat', 'b'))

    if number is None:
        return None

    letter = 'B' if scale_upper == 'MAJOR' else 'A'
    return f"{number}{letter}"


def get_compatible_keys(camelot: str) -> list:
    """
    Return list of Camelot keys harmonically compatible with the given key.

    Harmonic mixing rules:
    - ±1 number, same letter (adjacent keys on Camelot wheel)
    - Same number, opposite letter (relative major/minor)

    Args:
        camelot: Camelot notation (e.g., '8A', '5B')

    Returns:
        List of compatible Camelot keys (includes the input key)

    Examples:
        >>> get_compatible_keys('8A')
        ['7A', '8A', '9A', '8B']
        >>> get_compatible_keys('1B')
        ['12B', '1B', '2B', '1A']
        >>> get_compatible_keys('12A')
        ['11A', '12A', '1A', '12B']
    """
    if not camelot or len(camelot) < 2:
        return []

    # Parse number and letter
    try:
        # Handle 10A, 11A, 12A (two digits)
        if len(camelot) == 3:
            number = int(camelot[:2])
            letter = camelot[2].upper()
        else:
            number = int(camelot[0])
            letter = camelot[1].upper()
    except ValueError:
        return []

    if number < 1 or number > 12 or letter not in ('A', 'B'):
        return []

    # Calculate compatible keys
    prev_num = ((number - 2) % 12) + 1  # Wrap: 1→12, 12→11
    next_num = (number % 12) + 1  # Wrap: 12→1, 1→2
    opposite_letter = 'B' if letter == 'A' else 'A'

    return [
        f"{prev_num}{letter}",  # Previous number, same letter
        f"{number}{letter}",    # Exact match
        f"{next_num}{letter}",  # Next number, same letter
        f"{number}{opposite_letter}",  # Relative major/minor
    ]
