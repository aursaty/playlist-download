import pytest
from mutagen.id3 import ID3

from playlist_download import downloader
from playlist_download.downloader import DownloadError, download_audio, fetch_cover, tag_file
from playlist_download.models import Track

FAKE_MP3 = b"\xff\xfb\x90\x00" * 200


def make_track():
    return Track(position=3, title="Title", artists=["A", "B"], album="Album", duration_ms=200000,
                 isrc="USABC1234567", year=2021, explicit=False, cover_url=None)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(downloader.time, "sleep", lambda s: None)


def test_tag_file_writes_core_frames(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(FAKE_MP3)
    tag_file(f, make_track(), b"\x89PNG-fake-cover")
    tags = ID3(f)
    assert str(tags["TIT2"]) == "Title"
    assert str(tags["TPE1"]) == "A, B"
    assert str(tags["TALB"]) == "Album"
    assert str(tags["TDRC"]) == "2021"
    assert str(tags["TRCK"]) == "3"
    assert str(tags["TSRC"]) == "USABC1234567"
    assert tags.getall("APIC")[0].data == b"\x89PNG-fake-cover"


def test_tag_file_without_cover_or_optional_fields(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(FAKE_MP3)
    track = make_track()
    track.isrc, track.year = None, None
    tag_file(f, track, None)
    tags = ID3(f)
    assert str(tags["TIT2"]) == "Title"
    assert not tags.getall("APIC")
    assert "TSRC" not in tags


def test_download_audio_retries_then_raises(monkeypatch, tmp_path):
    calls = []

    def boom(url, dest):
        calls.append(url)
        raise RuntimeError("403")

    monkeypatch.setattr(downloader, "_run_ytdlp", boom)
    with pytest.raises(DownloadError):
        download_audio("https://youtube.com/watch?v=x", tmp_path / "a.mp3")
    assert len(calls) == 3


def test_download_audio_succeeds_after_one_failure(monkeypatch, tmp_path):
    dest = tmp_path / "a.mp3"
    attempts = []

    def flaky(url, d):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("temporary")
        d.write_bytes(FAKE_MP3)

    monkeypatch.setattr(downloader, "_run_ytdlp", flaky)
    download_audio("u", dest)
    assert dest.exists() and len(attempts) == 2


def test_download_audio_missing_output_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader, "_run_ytdlp", lambda url, dest: None)
    with pytest.raises(DownloadError):
        download_audio("u", tmp_path / "a.mp3")


def test_fetch_cover_none_url_returns_none():
    assert fetch_cover(None) is None


def test_fetch_cover_unreachable_returns_none():
    assert fetch_cover("http://127.0.0.1:1/cover.jpg") is None
