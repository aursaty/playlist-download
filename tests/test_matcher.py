from playlist_download.matcher import (
    pick_best,
    rank_candidates,
    ytmusic_result_to_candidate,
    youtube_entry_to_candidate,
)
from playlist_download.models import Candidate, Track


def make_track():
    return Track(position=1, title="Blinding Lights", artists=["The Weeknd"], album="After Hours",
                 duration_ms=200000, isrc=None, year=2020, explicit=False, cover_url=None)


def cand(video_id, title="Blinding Lights", channel="The Weeknd - Topic", duration_s=200, source="youtube"):
    return Candidate(url=f"https://www.youtube.com/watch?v={video_id}", source=source, title=title,
                     channel=channel, duration_s=duration_s, album=None)


def test_rank_sorts_by_score_desc():
    searcher = lambda q: [cand("bad", title="Other Song", channel="Nobody"), cand("good")]
    ranked = rank_candidates(make_track(), [searcher])
    assert [c.url.split("=")[1] for c in ranked] == ["good", "bad"]
    assert ranked[0].score > ranked[1].score


def test_rank_dedups_same_video_across_sources():
    a = lambda q: [cand("same", source="ytmusic")]
    b = lambda q: [cand("same", source="youtube")]
    assert len(rank_candidates(make_track(), [a, b])) == 1


def test_rank_dedups_music_and_plain_youtube_urls():
    a = lambda q: [Candidate("https://music.youtube.com/watch?v=abc", "ytmusic", "Blinding Lights",
                             "The Weeknd", 200, None)]
    b = lambda q: [cand("abc")]
    assert len(rank_candidates(make_track(), [a, b])) == 1


def test_rank_survives_searcher_exception():
    def boom(q):
        raise RuntimeError("network down")

    ranked = rank_candidates(make_track(), [boom, lambda q: [cand("ok")]])
    assert len(ranked) == 1


def test_rank_all_searchers_fail_returns_empty():
    def boom(q):
        raise RuntimeError("down")

    assert rank_candidates(make_track(), [boom]) == []


def test_pick_best_below_threshold_returns_none():
    ranked = rank_candidates(make_track(), [lambda q: [cand("x", title="Other", channel="Nobody")]])
    assert pick_best(ranked, threshold=70) is None


def test_pick_best_returns_top_when_above_threshold():
    ranked = rank_candidates(make_track(), [lambda q: [cand("good")]])
    assert pick_best(ranked, threshold=70) is ranked[0]


def test_pick_best_empty_returns_none():
    assert pick_best([], 70) is None


def test_ytmusic_result_mapping():
    result = {"videoId": "abc123", "title": "Blinding Lights", "artists": [{"name": "The Weeknd"}],
              "album": {"name": "After Hours"}, "duration_seconds": 200}
    c = ytmusic_result_to_candidate(result)
    assert (c.url, c.source, c.title, c.channel, c.duration_s, c.album) == (
        "https://music.youtube.com/watch?v=abc123", "ytmusic", "Blinding Lights", "The Weeknd", 200, "After Hours")


def test_ytmusic_result_without_album_or_duration_or_id():
    c = ytmusic_result_to_candidate({"videoId": "z", "title": "T", "artists": None, "album": None})
    assert (c.channel, c.album, c.duration_s) == ("", None, None)
    assert ytmusic_result_to_candidate({"title": "no id"}) is None


def test_youtube_entry_mapping():
    entry = {"id": "abc123", "title": "Blinding Lights", "channel": "The Weeknd - Topic", "duration": 200.0}
    c = youtube_entry_to_candidate(entry)
    assert (c.url, c.source, c.channel, c.duration_s) == (
        "https://www.youtube.com/watch?v=abc123", "youtube", "The Weeknd - Topic", 200)


def test_youtube_entry_falls_back_to_uploader_and_missing_duration():
    c = youtube_entry_to_candidate({"id": "q", "title": "T", "uploader": "Up", "duration": None})
    assert (c.channel, c.duration_s) == ("Up", None)
