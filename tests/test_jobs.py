import threading

import pytest

from playlist_download.downloader import DownloadError
from playlist_download.jobs import JobManager, ResolveError
from playlist_download.models import Candidate, Track
from playlist_download.report import TrackResult

PL = "37i9dQZF1DXcBWIGoYBM5M"
URL = f"https://open.spotify.com/playlist/{PL}"


def make_track(position):
    return Track(position=position, title=f"Song {position}", artists=["Artist"], album="Album",
                 duration_ms=200000, isrc=None, year=2020, explicit=False, cover_url="http://img/c.jpg")


def cand(n, score=50.0):
    return Candidate(url=f"https://www.youtube.com/watch?v=vid{n:08d}", source="youtube", title=f"Cand {n}",
                     channel="Chan", duration_s=200, album=None, score=score)


def fake_fetch(client, playlist_id):
    return "My List", [make_track(1), make_track(2), None, make_track(4)]


def fake_process(track, position, width, out_dir, threshold):
    if track is None:
        return TrackResult(position, None, "failed", None, [], "unavailable track")
    if position == 1:
        return TrackResult(position, track, "downloaded", cand(0, 95), [cand(0, 95)], None)
    return TrackResult(position, track, "failed", None, [cand(1), cand(2), cand(3)], "no match above threshold")


class Placer:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, track, url, width, out_dir):
        if self.error:
            raise self.error
        self.calls.append((track.position, url, width))
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{track.position:0{width}d} - Artist - {track.title}.mp3"
        path.write_bytes(b"audio")
        return path


def make_manager(tmp_path, placer=None, process=fake_process, fetch=fake_fetch):
    return JobManager(tmp_path, get_client=lambda: object(), process=process, fetch=fetch,
                      place=placer or Placer())


def started(tmp_path, **kw):
    mgr = make_manager(tmp_path, **kw)
    return mgr, mgr.start(URL, 70.0, background=False)


def test_start_runs_pipeline_and_ends_in_review(tmp_path):
    mgr, job = started(tmp_path)
    snap = mgr.snapshot(job)
    assert snap["status"] == "review"
    assert snap["name"] == "My List" and snap["total"] == 4
    assert [i["status"] for i in snap["items"]] == ["downloaded", "failed", "failed", "failed"]
    assert [r["position"] for r in snap["review"]] == [2, 4]  # unavailable item 3 is not reviewable
    assert (tmp_path / "My List" / "failed.txt").exists()


def test_all_downloaded_ends_done(tmp_path):
    def ok(track, position, width, out_dir, threshold):
        if track is None:
            return TrackResult(position, None, "failed", None, [], "unavailable track")
        return TrackResult(position, track, "downloaded", None, [], None)

    mgr, job = started(tmp_path, process=ok)
    assert mgr.snapshot(job)["status"] == "done"


def test_invalid_url_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        make_manager(tmp_path).start("https://example.com/nope", 70.0, background=False)


def test_invalid_threshold_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        make_manager(tmp_path).start(URL, 150.0, background=False)


def test_second_start_while_running_is_refused(tmp_path):
    gate = threading.Event()

    def slow(track, position, width, out_dir, threshold):
        gate.wait(5)
        return fake_process(track, position, width, out_dir, threshold)

    mgr = make_manager(tmp_path, process=slow)
    job = mgr.start(URL, 70.0)
    try:
        with pytest.raises(RuntimeError):
            mgr.start(URL, 70.0)
    finally:
        gate.set()
        job.thread.join(5)
    assert mgr.snapshot(job)["status"] == "review"


def test_fetch_error_sets_error_status(tmp_path):
    def boom(client, pid):
        raise RuntimeError("Spotify said no")

    mgr, job = started(tmp_path, fetch=boom)
    snap = mgr.snapshot(job)
    assert snap["status"] == "error" and "Spotify said no" in snap["error"]


def test_snapshot_review_card_fields(tmp_path):
    mgr, job = started(tmp_path)
    card = mgr.snapshot(job)["review"][0]
    assert card["track"]["title"] == "Song 2" and card["track"]["artists"] == ["Artist"]
    assert card["track"]["duration_s"] == 200 and card["track"]["cover_url"] == "http://img/c.jpg"
    assert card["candidates"][0]["video_id"] == "vid00000001"
    assert card["resolution"] is None


def test_accept_candidate_places_file_and_updates_state(tmp_path):
    placer = Placer()
    mgr, job = started(tmp_path, placer=placer)
    mgr.resolve(job.id, 2, "accept", candidate_index=1)
    assert placer.calls == [(2, cand(2).url, 1)]
    snap = mgr.snapshot(job)
    assert snap["items"][1]["status"] == "downloaded" and snap["items"][1]["resolution"] == "accepted"
    assert "Song 2" not in (tmp_path / "My List" / "failed.txt").read_text(encoding="utf-8")
    assert snap["status"] == "review"  # position 4 still open


def test_skip_everything_ends_done(tmp_path):
    mgr, job = started(tmp_path)
    mgr.resolve(job.id, 2, "skip")
    mgr.resolve(job.id, 4, "skip")
    snap = mgr.snapshot(job)
    assert snap["status"] == "done"
    assert [r["resolution"] for r in snap["review"]] == ["skipped", "skipped"]


def test_skipped_track_can_still_be_accepted_later(tmp_path):
    mgr, job = started(tmp_path)
    mgr.resolve(job.id, 2, "skip")
    mgr.resolve(job.id, 2, "accept", candidate_index=0)
    assert mgr.snapshot(job)["items"][1]["resolution"] == "accepted"


def test_accept_manual_youtube_url(tmp_path):
    placer = Placer()
    mgr, job = started(tmp_path, placer=placer)
    mgr.resolve(job.id, 2, "accept", url="https://youtu.be/manual123456")
    assert placer.calls[0][1] == "https://youtu.be/manual123456"


def test_accept_rejects_non_youtube_url(tmp_path):
    mgr, job = started(tmp_path)
    with pytest.raises(ValueError):
        mgr.resolve(job.id, 2, "accept", url="https://evil.com/x")


def test_accept_requires_valid_candidate_index(tmp_path):
    mgr, job = started(tmp_path)
    for bad in (None, -1, 9):
        with pytest.raises(ValueError):
            mgr.resolve(job.id, 2, "accept", candidate_index=bad)


def test_cannot_resolve_unavailable_or_downloaded_or_unknown(tmp_path):
    mgr, job = started(tmp_path)
    for position in (1, 3, 99):
        with pytest.raises(ValueError):
            mgr.resolve(job.id, position, "skip")


def test_unknown_action_and_unknown_job(tmp_path):
    mgr, job = started(tmp_path)
    with pytest.raises(ValueError):
        mgr.resolve(job.id, 2, "explode")
    with pytest.raises(KeyError):
        mgr.resolve("nope", 2, "skip")


def test_download_error_on_accept_keeps_track_unresolved(tmp_path):
    mgr, job = started(tmp_path, placer=Placer(error=DownloadError("403")))
    with pytest.raises(ResolveError, match="403"):
        mgr.resolve(job.id, 2, "accept", candidate_index=0)
    snap = mgr.snapshot(job)
    assert snap["items"][1]["status"] == "failed" and snap["review"][0]["resolution"] is None
