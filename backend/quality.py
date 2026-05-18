import subprocess
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

QUALITY_PRESETS = {
    "hi_res_lossless": {"min_bitrate": 1500, "label": "HiRes Lossless (24-bit)"},
    "high_lossless": {"min_bitrate": 700, "label": "Lossless (16-bit FLAC)"},
    "low_320k": {"min_bitrate": 300, "label": "High (320kbps AAC)"},
    "low_96k": {"min_bitrate": 64, "label": "Normal (96kbps AAC)"},
}

QUALITY_PRESETS_ORDER = list(QUALITY_PRESETS.keys())


def get_bitrate(file_path: str) -> Optional[int]:
    """Run ffprobe on a file and return the audio bitrate in kbps."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        for stream in streams:
            if stream.get("codec_type") == "audio":
                bitrate = int(stream.get("bit_rate", 0))
                if bitrate > 0:
                    return bitrate // 1000
        fmt_bitrate = int(data.get("format", {}).get("bit_rate", 0))
        if fmt_bitrate > 0:
            return fmt_bitrate // 1000
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"ffprobe failed for {file_path}: {e}")
        return None


def bitrate_meets_threshold(preset: str, actual_bitrate: int) -> bool:
    """Check if the actual bitrate meets the minimum threshold for a quality preset."""
    threshold = QUALITY_PRESETS.get(preset, {}).get("min_bitrate", 0)
    return actual_bitrate >= threshold
