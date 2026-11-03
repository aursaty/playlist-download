from playlist_download.models import Track
from playlist_download.naming import sanitize, track_filename


def make_track(position=1, title="Title", artists=("Artist",)):
    return Track(position=position, title=title, artists=list(artists), album="Album",
                 duration_ms=200000, isrc=None, year=2020, explicit=False, cover_url=None)


def test_sanitize_removes_illegal_chars():
    out = sanitize('a<b>:c"/d\e|f?g*')
    assert not any(ch in out for ch in '<>:"/\|?*')


def test_sanitize_strips_trailing_dots_and_spaces():
    assert sanitize("x. . ") == "x"


def test_sanitize_guards_reserved_names():
    assert sanitize("CON").upper() != "CON"


def test_track_filename_pads_to_width():
    name = track_filename(make_track(position=7), width=3)
    assert name.startswith("007 - ")
    assert name.endswith(".mp3")


def test_track_filename_joins_artists():
    name = track_filename(make_track(artists=("A", "B")), width=2)
    assert name == "01 - A, B - Title.mp3"


def test_track_filename_long_title_capped():
    name = track_filename(make_track(title="x" * 300), width=3)
    assert len(name[: -len(".mp3")]) <= 150


def test_track_filename_keeps_emoji_and_cyrillic():
    name = track_filename(make_track(title="Привет 🎵"), width=3)
    assert "Привет 🎵" in name


def test_duplicate_songs_get_distinct_names():
    a = track_filename(make_track(position=1), width=3)
    b = track_filename(make_track(position=2), width=3)
    assert a != b


def test_track_filename_respects_max_stem():
    name = track_filename(make_track(title="x" * 300), width=3, max_stem=60)
    assert len(name[: -len(".mp3")]) <= 60


def test_sanitize_empty_result_falls_back():
    assert sanitize("...") != ""
