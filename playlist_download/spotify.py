import json
import re
import urllib.error
import urllib.request

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
    track = item.get("track") or item.get("item")  # Spotify renamed track -> item in newer API versions
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
    data = client.playlist(playlist_id)
    page = data.get("tracks") or data.get("items")  # newer API versions renamed tracks -> items
    if not isinstance(page, dict) or "items" not in page:
        raise RuntimeError(
            f"Unexpected Spotify response: no track list found (keys: {sorted(data)}). "
            "Spotify may have changed its API, or the app cannot read this playlist."
        )
    tracks: list[Track | None] = []
    while True:
        for item in page["items"]:
            tracks.append(_to_track(len(tracks) + 1, item))
        if not page.get("next"):
            break
        page = client.next(page)
    return data["name"], tracks


# ---- public playlists ----------------------------------------------------------------------------
# Since early 2026 Spotify only lets apps like this read the tracks of playlists the logged-in user owns or
# collaborates on (403 for everyone else's, even public ones). The public embed page of a playlist still
# lists its first 100 tracks without any login, with less detail (no album, year, ISRC or cover).

EMBED_URL = "https://open.spotify.com/embed/playlist/{}"
EMBED_LIMIT = 100
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_REFUSED = (401, 403, 404)


class PlaylistUnavailable(Exception):
    """The playlist could not be read; the message says what the user can do."""


def parse_embed_html(html: str) -> tuple[str, list[Track | None]]:
    m = _NEXT_DATA.search(html)
    if not m:
        raise PlaylistUnavailable("The public playlist page had an unexpected format.")
    try:
        entity = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
        items = entity["trackList"]
        name = entity.get("name") or entity.get("title") or "playlist"
    except (ValueError, KeyError, TypeError) as exc:
        raise PlaylistUnavailable("The public playlist page had an unexpected format.") from exc
    return name, [_embed_track(i, item) for i, item in enumerate(items, start=1)]


def _embed_track(position: int, item: dict) -> Track | None:
    if not isinstance(item, dict) or item.get("entityType") != "track" or not str(item.get("uri", "")).startswith("spotify:track:"):
        return None
    artists = [a.strip() for a in str(item.get("subtitle", "")).split(",") if a.strip()]  # spotify joins artists with ", "
    return Track(
        position=position,
        title=item.get("title", ""),
        artists=artists,
        album="",
        duration_ms=int(item.get("duration") or 0),
        isrc=None,
        year=None,
        explicit=bool(item.get("isExplicit")),
        cover_url=None,
    )


def fetch_embed_playlist(playlist_id: str) -> tuple[str, list[Track | None]]:
    request = urllib.request.Request(EMBED_URL.format(playlist_id),
                                     headers={"User-Agent": _USER_AGENT, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PlaylistUnavailable(f"The public playlist page could not be loaded ({exc}).") from exc
    return parse_embed_html(html)


def fetch_playlist_any(client, playlist_id: str, fetch_official=fetch_playlist,
                       fetch_embed=fetch_embed_playlist) -> tuple[str, list[Track | None], str]:
    """Read a playlist with the best source available. `client` is None when nobody is logged in.

    Returns (name, tracks, notice); notice is empty unless the reduced public-page source was used.
    """
    refused = False
    if client is not None:
        try:
            name, tracks = fetch_official(client, playlist_id)
            return name, tracks, ""
        except spotipy.SpotifyException as exc:
            if exc.http_status not in _REFUSED:
                raise
            refused = True
        except RuntimeError:  # response without a track list: same restriction in another shape
            refused = True
    try:
        name, tracks = fetch_embed(playlist_id)
    except PlaylistUnavailable as exc:
        if refused:
            raise PlaylistUnavailable(
                "Spotify only lets this app read playlists you own or collaborate on, and the public page of "
                "this playlist was not available either. Check that the link is right and the playlist is public."
            ) from exc
        raise PlaylistUnavailable(
            "Could not read this playlist. If it is private, connect Spotify and try again."
        ) from exc
    notice = "Read from the public playlist page, no login: songs have no album or cover info."
    if len(tracks) >= EMBED_LIMIT:
        notice += f" Only the first {EMBED_LIMIT} songs are visible this way."
    return name, tracks, notice
