import re
from urllib.parse import parse_qs, urlparse

HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
_PATH_ID = re.compile(r"^/(?:shorts|embed|live|v)/([A-Za-z0-9_-]{6,20})")


def youtube_id(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in HOSTS:
        return None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
        return candidate if _ID.match(candidate) else None
    values = parse_qs(parsed.query).get("v", [])
    if values and _ID.match(values[0]):
        return values[0]
    m = _PATH_ID.match(parsed.path)
    return m.group(1) if m else None


def is_youtube_url(url: str) -> bool:
    try:
        scheme = urlparse(url).scheme
    except ValueError:
        return False
    return scheme in ("http", "https") and youtube_id(url) is not None
