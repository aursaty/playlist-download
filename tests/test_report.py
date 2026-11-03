import json

from playlist_download.models import Candidate, Track
from playlist_download.report import TrackResult, format_failed, summary, write_reports


def make_track(position, title="Song", artists=("Artist",)):
    return Track(position=position, title=title, artists=list(artists), album="Album",
                 duration_ms=200000, isrc=None, year=2020, explicit=False, cover_url=None)


def make_cand(i, score):
    return Candidate(url=f"https://youtube.com/watch?v={i}", source="youtube", title=f"Cand {i}",
                     channel="Chan", duration_s=200, album=None, score=score)


def downloaded(position):
    return TrackResult(position, make_track(position), "downloaded", make_cand(1, 95), [make_cand(1, 95)], None)


def failed(position, reason="no match above threshold", candidates=None):
    return TrackResult(position, make_track(position, "Lost Song", ("Band", "Guest")), "failed", None,
                       candidates or [], reason)


def test_summary_counts_existing_as_downloaded():
    results = [downloaded(1),
               TrackResult(2, make_track(2), "skipped_existing", None, [], None),
               failed(3)]
    assert summary(results) == "2 downloaded / 1 failed"


def test_failed_text_includes_reason_and_best_rejected():
    results = [downloaded(1), failed(2, candidates=[make_cand(7, 55.5), make_cand(8, 40)])]
    text = format_failed(results)
    assert text == (
        "2 | Band, Guest | Lost Song | no match above threshold | "
        "best rejected: Cand 7 (55.5) https://youtube.com/watch?v=7"
    )


def test_failed_text_pads_position_to_playlist_width():
    results = [downloaded(i) for i in range(1, 100)] + [failed(100)]
    assert format_failed(results).startswith("100 | ")
    results = [failed(5)] + [downloaded(i) for i in range(2, 12)]
    assert format_failed(results).startswith("05 | ")


def test_failed_text_without_candidates_has_no_suffix():
    assert "best rejected" not in format_failed([failed(1)])


def test_failed_text_handles_unusable_item():
    unusable = TrackResult(2, None, "failed", None, [], "unavailable track")
    assert format_failed([downloaded(1), unusable]) == "2 | (unavailable track) | unavailable track"


def test_report_json_has_top5_candidates_only(tmp_path):
    cands = [make_cand(i, 90 - i) for i in range(8)]
    write_reports(tmp_path, [failed(1, candidates=cands)])
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    entry = data["tracks"][0]
    assert entry["status"] == "failed"
    assert entry["reason"] == "no match above threshold"
    assert len(entry["candidates"]) == 5
    assert entry["candidates"][0]["url"] == "https://youtube.com/watch?v=0"
    assert entry["track"]["title"] == "Lost Song"
    assert data["summary"] == "0 downloaded / 1 failed"


def test_report_json_unusable_track_is_null(tmp_path):
    write_reports(tmp_path, [TrackResult(1, None, "failed", None, [], "unavailable track")])
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert data["tracks"][0]["track"] is None


def test_no_failures_writes_empty_failed_file(tmp_path):
    write_reports(tmp_path, [downloaded(1)])
    assert (tmp_path / "failed.txt").read_text(encoding="utf-8") == ""


def test_unicode_survives_in_failed_file(tmp_path):
    res = TrackResult(1, make_track(1, "Привет 🎵", ("Артист",)), "failed", None, [], "download error: x")
    write_reports(tmp_path, [res])
    assert "Привет 🎵" in (tmp_path / "failed.txt").read_text(encoding="utf-8")
