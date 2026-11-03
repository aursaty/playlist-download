import os
import shutil
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"


class ConfigError(Exception):
    pass


@dataclass
class Config:
    client_id: str
    redirect_uri: str


def load_config() -> Config:
    load_dotenv()
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    if not client_id:
        raise ConfigError("SPOTIFY_CLIENT_ID missing. Set it in .env (Spotify app Client ID).")
    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "").strip() or DEFAULT_REDIRECT_URI
    return Config(client_id=client_id, redirect_uri=redirect_uri)


def check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise ConfigError("ffmpeg not found on PATH. Install it (e.g. `winget install Gyan.FFmpeg`).")
