from pathlib import Path

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyPKCE

from playlist_download.config import Config
from playlist_download.spotify import SCOPE


class WebAuth:
    """Spotify login driven from the web page: no browser has to open on the server (works in Docker)."""

    def __init__(self, config: Config, cache_path: Path):
        self._auth = SpotifyPKCE(
            client_id=config.client_id,
            redirect_uri=config.web_redirect_uri,
            scope=SCOPE,
            cache_handler=CacheFileHandler(cache_path=str(cache_path)),
            open_browser=False,
        )

    def connected(self) -> bool:
        try:
            return self._auth.validate_token(self._auth.cache_handler.get_cached_token()) is not None
        except Exception:
            return False

    def login_url(self) -> str:
        return self._auth.get_authorize_url()

    def finish(self, code: str) -> None:
        self._auth.get_access_token(code=code, check_cache=False)

    def client(self) -> spotipy.Spotify:
        return spotipy.Spotify(auth_manager=self._auth)
