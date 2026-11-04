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


def test_short_artist_name_is_not_substring_matched():
    track = make_track(artists=("Sia",))
    cand = make_cand(channel="Asia", title="Blinding Lights")
    assert score_candidate(track, cand) < 70


def test_live_only_upload_below_default_threshold():
    track = make_track(title="Hello", artists=("Adele",), duration_ms=295000)
    cand = make_cand(title="Hello (Live at the BBC)", channel="Adele - Topic", duration_s=296)
    assert score_candidate(track, cand) < 70


def test_different_remix_in_brackets_penalized():
    track = make_track(title="Song (A Remix)", artists=("X",), duration_ms=200000)
    cand = make_cand(title="Song (B Remix)", channel="X - Topic", duration_s=200)
    assert score_candidate(track, cand) < 70


def test_matching_remix_in_brackets_still_passes():
    track = make_track(title="Song (A Remix)", artists=("X",), duration_ms=200000)
    cand = make_cand(title="Song (A Remix)", channel="X - Topic", duration_s=200)
    assert score_candidate(track, cand) >= 90


def test_title_with_many_extra_words_is_not_a_perfect_match():
    track = make_track(title="Intro", artists=("X",), duration_ms=200000)
    cand = make_cand(title="Intro to the Outro (Interlude)", channel="X - Topic", duration_s=200)
    assert score_candidate(track, cand) < 70


def test_official_audio_suffix_not_penalized():
    cand = make_cand(title="The Weeknd - Blinding Lights (Official Audio)", channel="The Weeknd")
    assert score_candidate(make_track(), cand) >= 85


def test_cyrillic_artist_matches_latin_spotify_artist():
    track = make_track(title="Hip-Hop", artists=("Boombox",), duration_ms=229000)
    cand = make_cand(title="Hip-Hop", channel="БумБокс", source="ytmusic", duration_s=230)
    assert score_candidate(track, cand) >= 90


def test_cyrillic_title_and_artist_match_latin_artist():
    track = make_track(title="Поп корн", artists=("Tartak",), duration_ms=194000)
    cand = make_cand(title="Поп Корн", channel="Тартак", source="ytmusic", duration_s=195)
    assert score_candidate(track, cand) >= 90


def test_unrelated_title_with_artist_word_capped_below_threshold():
    track = make_track(title="Hip-Hop", artists=("Boombox",), duration_ms=229000)
    cand = make_cand(title="The Boombox Saints", channel="RedCloud - Topic", duration_s=225)
    assert score_candidate(track, cand) < 70


def test_latin_title_matches_cyrillic_transliteration():
    track = make_track(title="Pop Korn", artists=("Tartak",), duration_ms=194000)
    cand = make_cand(title="Поп Корн", channel="Тартак", duration_s=194)
    assert score_candidate(track, cand) >= 90


def test_different_artist_other_script_still_rejected():
    track = make_track(title="Hip-Hop", artists=("Boombox",), duration_ms=229000)
    cand = make_cand(title="Hip-Hop", channel="Тартак", duration_s=229)
    assert score_candidate(track, cand) < 70


def test_mix_version_penalized_when_not_in_spotify_title():
    track = make_track(title="Pop Corn", artists=("Tartak",), duration_ms=194000)
    cand = make_cand(title="Pop Corn (VS & FDR POP BASS MIX)", channel="Tartak", duration_s=194)
    assert score_candidate(track, cand) < 70


def test_mix_not_penalized_when_in_spotify_title():
    track = make_track(title="Pop Corn (Radio Mix)", artists=("Tartak",), duration_ms=194000)
    cand = make_cand(title="Pop Corn (Radio Mix)", channel="Tartak", duration_s=194)
    assert score_candidate(track, cand) >= 90
