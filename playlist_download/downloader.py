import time
import urllib.request
from pathlib import Path

from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TRCK, TSRC, ID3NoHeaderError

from playlist_download.models import Track

RETRIES = 2  # retries after the first attempt
PNG_MAGIC = b"\x89PNG"


class DownloadError(Exception):
    pass


def _run_ytdlp(url: str, dest: Path) -> None:
    from yt_dlp import YoutubeDL

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(dest.with_suffix("")) + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}
        ],
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([url])


def download_audio(url: str, dest: Path) -> None:
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            _run_ytdlp(url, dest)
            if not dest.exists():
                raise DownloadError(f"yt-dlp produced no file at {dest.name}")
            return
        except Exception as exc:
            last = exc
            if attempt < RETRIES:
                time.sleep(2 * (attempt + 1))
    raise DownloadError(str(last)) from last


def fetch_cover(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.read()
    except Exception:
        return None


def tag_file(path: Path, track: Track, cover_bytes: bytes | None) -> None:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(TIT2(encoding=3, text=track.title))
    tags.add(TPE1(encoding=3, text=", ".join(track.artists)))
    tags.add(TALB(encoding=3, text=track.album))
    tags.add(TRCK(encoding=3, text=str(track.position)))
    if track.year:
        tags.add(TDRC(encoding=3, text=str(track.year)))
    if track.isrc:
        tags.add(TSRC(encoding=3, text=track.isrc))
    if cover_bytes:
        mime = "image/png" if cover_bytes.startswith(PNG_MAGIC) else "image/jpeg"
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover_bytes))
    tags.save(path, v2_version=3)
