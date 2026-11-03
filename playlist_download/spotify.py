import re

import spotipy
from spotipy.oauth2 import SpotifyPKCE

from playlist_download.config import Config
from playlist_download.models import Track

SCOPE = "playlist-read-private playlist-read-collaborative"
_ID = r"[A-Za-z0-9]{22}"
_PATTERNS = [
    re.compile(rf"open\.spotify\.com/(?:intl-[a-z]+/)?playlist/({_ID})"),
    re.compile(rf"^spotify:playlist:({_ID})$"),
    re.compile(rf"^({_ID})$"),
]
_FIELDS = (
    "name,tracks.next,tracks.items(is_local,track(type,name,duration_ms,explicit,is_local,"
    "external_ids,artists(name),album(name,release_date,images)))"
)


def parse_playlist_id(url_or_id: str) -> str:
    value = url_or_id.strip()
    for pattern in _PATTERNS:
        m = pattern.search(value)
        if m:
            return m.group(1)
    raise ValueError(f"Not a Spotify playlist URL, URI or id: {url_or_id!r}")


def make_client(config: Config) -> spotipy.Spotify:
    auth = SpotifyPKCE(client_id=config.client_id, redirect_uri=config.redirect_uri, scope=SCOPE)
    return spotipy.Spotify(auth_manager=auth)


def _to_track(position: int, item: dict) -> Track | None:
    track = item.get("track")
    if not track or item.get("is_local") or track.get("is_local") or track.get("type") != "track":
        return None
    album = track.get("album") or {}
    release = album.get("release_date") or ""
    images = album.get("images") or []
    return Track(
        position=position,
        title=track["name"],
        artists=[a["name"] for a in track.get("artists", [])],
        album=album.get("name", ""),
        duration_ms=track.get("duration_ms", 0),
        isrc=(track.get("external_ids") or {}).get("isrc"),
        year=int(release[:4]) if release[:4].isdigit() else None,
        explicit=bool(track.get("explicit")),
        cover_url=images[0]["url"] if images else None,
    )


def fetch_playlist(client, playlist_id: str) -> tuple[str, list[Track | None]]:
    data = client.playlist(playlist_id, fields=_FIELDS)
    page = data["tracks"]
    tracks: list[Track | None] = []
    while True:
        for item in page["items"]:
            tracks.append(_to_track(len(tracks) + 1, item))
        if not page.get("next"):
            break
        page = client.next(page)
    return data["name"], tracks
