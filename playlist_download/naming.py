import re
from pathlib import Path

from playlist_download.models import Track

MAX_STEM = 150
MAX_FOLDER_NAME = 60
_BACKSLASH = chr(92)
_ILLEGAL = re.compile("[" + re.escape('<>:"/|?*' + _BACKSLASH) + r"\x00-\x1f]")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def sanitize(name: str) -> str:
    out = _ILLEGAL.sub("_", name).rstrip(". ")
    if not out:
        return "_"
    if out.split(".")[0].upper() in _RESERVED:
        out = "_" + out
    return out


def track_filename(track: Track, width: int, max_stem: int = MAX_STEM) -> str:
    prefix = f"{track.position:0{width}d} - "
    body = sanitize(f"{', '.join(track.artists)} - {track.title}")
    stem = (prefix + body)[:max_stem].rstrip(". ")
    return stem + ".mp3"


def playlist_folder(base: Path, name: str) -> Path:
    return base / sanitize(name)[:MAX_FOLDER_NAME].rstrip(". ")
