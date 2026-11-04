from urllib.parse import parse_qs, urlparse

from playlist_download.config import Config
from playlist_download.webauth import WebAuth


def make_auth(tmp_path):
    cfg = Config("client123", "http://127.0.0.1:8888/callback", "http://127.0.0.1:8000/callback")
    return WebAuth(cfg, tmp_path / ".cache-web")


def test_not_connected_without_cached_token(tmp_path):
    assert make_auth(tmp_path).connected() is False


def test_login_url_uses_web_redirect_pkce_and_scope(tmp_path):
    url = make_auth(tmp_path).login_url()
    q = parse_qs(urlparse(url).query)
    assert q["client_id"] == ["client123"]
    assert q["redirect_uri"] == ["http://127.0.0.1:8000/callback"]
    assert q["code_challenge_method"] == ["S256"] and q["code_challenge"]
    assert "playlist-read-private" in q["scope"][0]
