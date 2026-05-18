import subprocess
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def convert_format(
    input_path: str,
    output_path: str,
    target_format: str,
    bitrate: Optional[str] = None,
) -> str:
    """Convert an audio file to a target format using ffmpeg.

    If the target format matches the source format (both FLAC), returns input_path as-is.
    Returns the output_path on success.
    """
    input_ext = os.path.splitext(input_path)[1].lower().lstrip(".")
    target_fmt = target_format.lower()

    if input_ext == target_fmt:
        logger.info(f"Source is already {target_fmt}, skipping conversion")
        return input_path

    codec_map = {
        "mp3": "libmp3lame",
        "m4a": "aac",
        "flac": "flac",
    }
    codec = codec_map.get(target_fmt, "copy")

    cmd = ["ffmpeg", "-y", "-i", input_path]

    if target_fmt in ("mp3", "m4a") and bitrate:
        cmd += ["-c:a", codec, "-b:a", bitrate]
    else:
        cmd += ["-c:a", codec]

    cmd.append(output_path)

    logger.info(f"Converting {input_path} -> {output_path} ({target_fmt}, {codec})")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.error(f"ffmpeg conversion failed: {result.stderr}")
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")

    return output_path
