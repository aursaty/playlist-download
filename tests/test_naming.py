from playlist_download.models import Track
from playlist_download.naming import find_existing, sanitize, track_filename


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


def test_find_existing_by_prefix(tmp_path):
    f = tmp_path / "003 - A - B.mp3"
    f.write_bytes(b"x")
    assert find_existing(tmp_path, 3, 3) == f
    assert find_existing(tmp_path, 4, 3) is None


def test_find_existing_missing_dir_returns_none(tmp_path):
    assert find_existing(tmp_path / "nope", 1, 3) is None
