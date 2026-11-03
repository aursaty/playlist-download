from playlist_download.models import Candidate, Track
from playlist_download.scoring import normalize, score_candidate


def make_track(title="Blinding Lights", artists=("The Weeknd",), album="After Hours", duration_ms=200000):
    return Track(position=1, title=title, artists=list(artists), album=album,
                 duration_ms=duration_ms, isrc=None, year=2020, explicit=False, cover_url=None)


def make_cand(title="Blinding Lights", channel="The Weeknd - Topic", duration_s=200,
              source="youtube", album=None):
    return Candidate(url="https://youtube.com/watch?v=x", source=source, title=title,
                     channel=channel, duration_s=duration_s, album=album)


def test_exact_topic_match_scores_high():
    assert score_candidate(make_track(), make_cand()) >= 90


def test_duration_off_by_20s_gets_no_duration_points():
    exact = score_candidate(make_track(), make_cand(duration_s=200))
    far = score_candidate(make_track(), make_cand(duration_s=220))
    assert exact - far >= 39


def test_live_version_penalized():
    studio = score_candidate(make_track(), make_cand())
    live = score_candidate(make_track(), make_cand(title="Blinding Lights (Live)"))
    assert studio - live >= 25


def test_live_not_penalized_when_in_spotify_title():
    track = make_track(title="Blinding Lights - Live")
    cand = make_cand(title="Blinding Lights - Live")
    assert score_candidate(track, cand) >= 90


def test_missing_duration_does_not_crash_and_cannot_pass_threshold_alone():
    cand = make_cand(title="Totally Different Song", channel="Someone Else", duration_s=None)
    assert score_candidate(make_track(), cand) < 70


def test_missing_duration_cannot_reach_perfect_score():
    assert score_candidate(make_track(), make_cand(duration_s=None)) < 70 + 30


def test_cyrillic_title_normalizes_non_empty():
    assert normalize("Привет") != ""


def test_japanese_title_normalizes_non_empty():
    assert normalize("夜に駆ける") != ""


def test_feat_and_brackets_stripped():
    assert normalize("Song (feat. X)") == normalize("Song")


def test_wrong_artist_scores_below_threshold():
    cand = make_cand(channel="Random Channel", title="Blinding Lights", duration_s=200)
    assert score_candidate(make_track(), cand) < 70


def test_wrong_artist_and_title_below_threshold():
    cand = make_cand(channel="Random Channel", title="Other Song", duration_s=200)
    assert score_candidate(make_track(), cand) < 70


def test_ytmusic_album_match_gives_bonus():
    without = score_candidate(make_track(), make_cand(channel="The Weeknd", source="ytmusic", album=None))
    with_album = score_candidate(make_track(), make_cand(channel="The Weeknd", source="ytmusic", album="After Hours"))
    assert with_album > without


def test_score_clamped_to_0_100():
    s = score_candidate(make_track(), make_cand(title="Blinding Lights live cover remix karaoke", channel="x"))
    assert 0 <= s <= 100
