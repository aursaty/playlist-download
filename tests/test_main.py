import os

import pytest

from playlist_download import main as app
from playlist_download.config import Config, ConfigError
from playlist_download.downloader import DownloadError
from playlist_download.main import process_track
from playlist_download.models import Candidate, Track
from playlist_download.report import TrackResult


def make_track(position=1):
    return Track(position=position, title="Title", artists=["Artist"], album="Album", duration_ms=200000,
                 isrc=None, year=2020, explicit=False, cover_url=None)


def cand(score):
    return Candidate(url="https://youtube.com/watch?v=x", source="youtube", title="T", channel="C",
                     duration_s=200, album=None, score=score)


def good_download(url, dest):
    dest.write_bytes(b"audio")


def run(tmp_path, track=None, rank=None, download=good_download, tag=lambda p, t, c: None, position=1, width=2):
    return process_track(
        make_track(position) if track is None else track, position, width, tmp_path, 70,
        rank=rank or (lambda t: [cand(95)]), download=download, tag=tag, cover=lambda url: None,
    )


def test_process_track_downloads_and_names_file(tmp_path):
    result = run(tmp_path)
    assert result.status == "downloaded"
    assert [p.name for p in tmp_path.iterdir()] == ["01 - Artist - Title.mp3"]
    assert result.chosen.score == 95


def test_process_track_skips_existing(tmp_path):
    (tmp_path / "01 - Artist - Title.mp3").write_bytes(b"x")

    def must_not_rank(track):
        raise AssertionError("rank called")

    result = run(tmp_path, rank=must_not_rank)
    assert result.status == "skipped_existing"


def test_process_track_no_match_records_candidates(tmp_path):
    result = run(tmp_path, rank=lambda t: [cand(40), cand(30)])
    assert result.status == "failed"
    assert result.reason == "no match above threshold"
    assert len(result.candidates) == 2
    assert list(tmp_path.iterdir()) == []


def test_process_track_download_error_recorded_not_raised(tmp_path):
    def bad(url, dest):
        raise DownloadError("403 forbidden")

    result = run(tmp_path, download=bad)
    assert result.status == "failed"
    assert result.reason == "download error: 403 forbidden"
    assert result.candidates and result.candidates[0].score == 95


def test_process_track_unavailable_item(tmp_path):
    result = process_track(None, 4, 2, tmp_path, 70)
    assert (result.status, result.reason, result.position, result.track) == ("failed", "unavailable track", 4, None)


def test_partial_file_not_left_on_failure(tmp_path):
    def partial_then_fail(url, dest):
        dest.write_bytes(b"half")
        raise DownloadError("connection reset")

    run(tmp_path, download=partial_then_fail)
    assert list(tmp_path.iterdir()) == []


def test_tag_failure_recorded_and_no_file_left(tmp_path):
    def bad_tag(path, track, cover):
        raise ValueError("corrupt")

    result = run(tmp_path, tag=bad_tag)
    assert result.status == "failed"
    assert result.reason.startswith("tagging error")
    assert list(tmp_path.iterdir()) == []


def test_rank_exception_recorded_not_raised(tmp_path):
    def boom(track):
        raise RuntimeError("search exploded")

    result = run(tmp_path, rank=boom)
    assert result.status == "failed"
    assert "search exploded" in result.reason


def test_duplicate_songs_do_not_collide(tmp_path):
    run(tmp_path, position=1)
    run(tmp_path, position=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["01 - Artist - Title.mp3", "02 - Artist - Title.mp3"]


def test_main_invalid_playlist_returns_2(capsys):
    assert app.main(["not a playlist"]) == 2


def test_main_config_error_returns_2(monkeypatch):
    monkeypatch.setattr(app, "check_ffmpeg", lambda: (_ for _ in ()).throw(ConfigError("no ffmpeg")))
    assert app.main(["37i9dQZF1DXcBWIGoYBM5M"]) == 2


def test_main_writes_reports_and_returns_0_with_failures(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "check_ffmpeg", lambda: None)
    monkeypatch.setattr(app, "load_config", lambda: Config("id", "uri"))
    monkeypatch.setattr(app, "make_client", lambda cfg: object())
    monkeypatch.setattr(app, "fetch_playlist", lambda client, pid: ("My: List?", [make_track(1), None]))

    def fake_process(track, position, width, out_dir, threshold, **kw):
        if track is None:
            return TrackResult(position, None, "failed", None, [], "unavailable track")
        return TrackResult(position, track, "downloaded", None, [], None)

    monkeypatch.setattr(app, "process_track", fake_process)
    code = app.main(["37i9dQZF1DXcBWIGoYBM5M", "--out", str(tmp_path)])
    assert code == 0
    out = tmp_path / "My_ List_"
    assert "unavailable track" in (out / "failed.txt").read_text(encoding="utf-8")
    assert (out / "report.json").exists()


def test_existing_file_for_other_song_at_same_position_is_not_skipped(tmp_path):
    (tmp_path / "01 - Someone Else - Old Song.mp3").write_bytes(b"x")
    result = run(tmp_path)
    assert result.status == "downloaded"


def test_os_error_on_replace_recorded_not_raised(tmp_path, monkeypatch):
    def deny(src, dst):
        raise PermissionError("file in use")

    monkeypatch.setattr(os, "replace", deny)
    result = run(tmp_path)
    assert result.status == "failed"
    assert result.reason.startswith("file error")
    assert list(tmp_path.iterdir()) == []


def test_long_output_dir_shortens_filename(tmp_path):
    deep = tmp_path / ("d" * 50) / ("e" * 50)
    long_track = make_track(1)
    long_track.title = "t" * 200
    result = process_track(long_track, 1, 2, deep, 70, rank=lambda t: [cand(95)], download=good_download,
                           tag=lambda p, t, c: None, cover=lambda u: None)
    assert result.status == "downloaded"
    (f,) = list(deep.iterdir())
    assert len(str(f.resolve())) <= 255


def test_main_writes_reports_on_keyboard_interrupt(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "check_ffmpeg", lambda: None)
    monkeypatch.setattr(app, "load_config", lambda: Config("id", "uri"))
    monkeypatch.setattr(app, "make_client", lambda cfg: object())
    monkeypatch.setattr(app, "fetch_playlist", lambda client, pid: ("PL", [make_track(1), make_track(2)]))

    def fake_process(track, position, width, out_dir, threshold, **kw):
        if position == 2:
            raise KeyboardInterrupt
        return TrackResult(position, track, "failed", None, [], "no match above threshold")

    monkeypatch.setattr(app, "process_track", fake_process)
    code = app.main(["37i9dQZF1DXcBWIGoYBM5M", "--out", str(tmp_path)])
    assert code == 130
    assert "no match above threshold" in (tmp_path / "PL" / "failed.txt").read_text(encoding="utf-8")
