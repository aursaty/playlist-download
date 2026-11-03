import re
from pathlib import Path

from playlist_download.models import Track

MAX_STEM = 150
_BACKSLASH = chr(92)
_ILLEGAL = re.compile("[" + re.escape('<>:"/|?*' + _BACKSLASH) + r"\x00-\x1f]")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def sanitize(name: str) -> str:
    out = _ILLEGAL.sub("_", name).rstrip(". ")
    if out.upper() in _RESERVED:
        out += "_"
    return out


def track_filename(track: Track, width: int) -> str:
    prefix = f"{track.position:0{width}d} - "
    body = sanitize(f"{', '.join(track.artists)} - {track.title}")
    stem = (prefix + body)[:MAX_STEM].rstrip(". ")
    return stem + ".mp3"


def find_existing(out_dir: Path, position: int, width: int) -> Path | None:
    if not out_dir.is_dir():
        return None
    prefix = f"{position:0{width}d} - "
    for f in sorted(out_dir.glob("*.mp3")):
        if f.name.startswith(prefix):
            return f
    return None
