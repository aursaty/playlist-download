import pytest

from playlist_download import config
from playlist_download.config import ConfigError, check_ffmpeg, load_config


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)


def test_load_config_defaults_redirect_uri(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "abc")
    cfg = load_config()
    assert cfg.client_id == "abc"
    assert cfg.redirect_uri == "http://127.0.0.1:8888/callback"


def test_load_config_missing_client_id_raises():
    with pytest.raises(ConfigError):
        load_config()


def test_check_ffmpeg_missing_raises(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    with pytest.raises(ConfigError):
        check_ffmpeg()


def test_web_redirect_uri_default_and_override(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "abc")
    assert load_config().web_redirect_uri == "http://127.0.0.1:8000/callback"
    monkeypatch.setenv("WEB_REDIRECT_URI", "http://localhost:9000/callback")
    assert load_config().web_redirect_uri == "http://localhost:9000/callback"
