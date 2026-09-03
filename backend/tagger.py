import logging
from pathlib import Path
from typing import Optional

import requests
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TCON, TDRC, TPUB, TSRC, TBPM, TKEY, APIC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover

logger = logging.getLogger(__name__)


def tag_file(file_path: str, metadata: dict, cover_art_url: Optional[str] = None):
    """Tag an audio file with extended metadata."""
    ext = Path(file_path).suffix.lower()
    if ext == ".flac":
        _tag_flac(file_path, metadata, cover_art_url)
    elif ext == ".mp3":
        _tag_mp3(file_path, metadata, cover_art_url)
    elif ext == ".m4a":
        _tag_m4a(file_path, metadata, cover_art_url)
    else:
        logger.warning(f"Unsupported format for tagging: {ext}")


def tag_dj_metadata(file_path: str, camelot: Optional[str], bpm: Optional[float] = None):
    """Write DJ-standard Key (Camelot notation) and BPM tags for Rekordbox/Serato/VirtualDJ."""
    ext = Path(file_path).suffix.lower()
    bpm_int = round(bpm) if bpm else None
    try:
        if ext == ".flac":
            f = FLAC(file_path)
            if camelot:
                f["initialkey"] = [camelot]
            if bpm_int:
                f["bpm"] = [str(bpm_int)]
            f.save()
        elif ext == ".mp3":
            f = MP3(file_path)
            if f.tags is None:
                f.add_tags()
            if camelot:
                f.tags["TKEY"] = TKEY(encoding=3, text=camelot)
            if bpm_int:
                f.tags["TBPM"] = TBPM(encoding=3, text=str(bpm_int))
            f.save()
        elif ext == ".m4a":
            f = MP4(file_path)
            if f.tags is None:
                f.add_tags()
            if camelot:
                f.tags["----:com.apple.iTunes:initialkey"] = [camelot.encode("utf-8")]
            if bpm_int:
                f.tags["tmpo"] = [bpm_int]
            f.save()
    except Exception as e:
        logger.warning(f"Failed to write DJ metadata tags to {file_path}: {e}")


def _get_cover_bytes(metadata: dict, cover_art_url: Optional[str] = None) -> Optional[bytes]:
    local_path = metadata.get("cover_art_path")
    if local_path and Path(local_path).exists():
        return Path(local_path).read_bytes()
    if cover_art_url:
        try:
            resp = requests.get(cover_art_url, timeout=10)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            logger.warning(f"Failed to download cover art: {e}")
    return None


def _tag_flac(file_path: str, metadata: dict, cover_art_url: Optional[str] = None):
    f = FLAC(file_path)
    f.delete()

    if metadata.get("title"):
        f["title"] = [metadata["title"]]
    if metadata.get("artist"):
        f["artist"] = [metadata["artist"]]
    if metadata.get("album"):
        f["album"] = [metadata["album"]]
    if metadata.get("track_num"):
        f["tracknumber"] = [str(metadata["track_num"])]
    if metadata.get("genre"):
        f["genre"] = [metadata["genre"]]
    if metadata.get("year"):
        f["date"] = [str(metadata["year"])]
    if metadata.get("label"):
        f["label"] = [metadata["label"]]
    if metadata.get("isrc"):
        f["isrc"] = [metadata["isrc"]]
    if metadata.get("bpm") and metadata["bpm"] > 0:
        f["bpm"] = [str(metadata["bpm"])]
    if metadata.get("key"):
        f["initialkey"] = [metadata["key"]]

    cover_bytes = _get_cover_bytes(metadata, cover_art_url)
    if cover_bytes:
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.data = cover_bytes
        f.add_picture(pic)

    f.save()


def _tag_mp3(file_path: str, metadata: dict, cover_art_url: Optional[str] = None):
    f = MP3(file_path)
    if f.tags is None:
        f.add_tags()
    f.tags.delall("APIC")

    tags = []
    if metadata.get("title"):
        tags.append(TIT2(encoding=3, text=metadata["title"]))
    if metadata.get("artist"):
        tags.append(TPE1(encoding=3, text=metadata["artist"]))
    if metadata.get("album"):
        tags.append(TALB(encoding=3, text=metadata["album"]))
    if metadata.get("track_num"):
        tags.append(TRCK(encoding=3, text=str(metadata["track_num"])))
    if metadata.get("genre"):
        tags.append(TCON(encoding=3, text=metadata["genre"]))
    if metadata.get("year"):
        tags.append(TDRC(encoding=3, text=str(metadata["year"])))
    if metadata.get("label"):
        tags.append(TPUB(encoding=3, text=metadata["label"]))
    if metadata.get("isrc"):
        tags.append(TSRC(encoding=3, text=metadata["isrc"]))
    if metadata.get("bpm") and metadata["bpm"] > 0:
        tags.append(TBPM(encoding=3, text=str(metadata["bpm"])))
    if metadata.get("key"):
        tags.append(TKEY(encoding=3, text=metadata["key"]))

    cover_bytes = _get_cover_bytes(metadata, cover_art_url)
    if cover_bytes:
        tags.append(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes))

    for tag in tags:
        f.tags.add(tag)
    f.save()


def _tag_m4a(file_path: str, metadata: dict, cover_art_url: Optional[str] = None):
    f = MP4(file_path)
    if f.tags is None:
        f.add_tags()

    if metadata.get("title"):
        f.tags["\xa9nam"] = [metadata["title"]]
    if metadata.get("artist"):
        f.tags["\xa9ART"] = [metadata["artist"]]
    if metadata.get("album"):
        f.tags["\xa9alb"] = [metadata["album"]]
    if metadata.get("track_num"):
        f.tags["trkn"] = [(metadata["track_num"], 0)]
    if metadata.get("genre"):
        f.tags["\xa9gen"] = [metadata["genre"]]
    if metadata.get("year"):
        f.tags["\xa9DAY"] = [str(metadata["year"])]
    if metadata.get("label"):
        f.tags["----:com.apple.iTunes:LABEL"] = [metadata["label"].encode("utf-8")]
    if metadata.get("isrc"):
        f.tags["----:com.apple.iTunes:ISRC"] = [metadata["isrc"].encode("utf-8")]
    if metadata.get("bpm") and metadata["bpm"] > 0:
        f.tags["tmpo"] = [metadata["bpm"]]
    if metadata.get("key"):
        f.tags["----:com.apple.iTunes:initialkey"] = [metadata["key"].encode("utf-8")]

    cover_bytes = _get_cover_bytes(metadata, cover_art_url)
    if cover_bytes:
        f.tags["covr"] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]

    f.save()
