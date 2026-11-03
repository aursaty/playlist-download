import pytest

from playlist_download.spotify import fetch_playlist, parse_playlist_id

PID = "37i9dQZF1DXcBWIGoYBM5M"


def make_item(n, **overrides):
    track = {
        "type": "track",
        "name": f"Song {n}",
        "artists": [{"name": "A"}, {"name": "B"}],
        "album": {"name": "Album", "release_date": "2021-05-01",
                  "images": [{"url": "http://img/big"}, {"url": "http://img/small"}]},
        "duration_ms": 180000 + n,
        "external_ids": {"isrc": f"ISRC{n}"},
        "explicit": True,
        "is_local": False,
    }
    track.update(overrides)
    return {"track": track, "is_local": False}


class FakeClient:
    def __init__(self, pages, name="My List"):
        self.name = name
        self.pages = pages  # list of lists of items

    def _page(self, i):
        nxt = f"page{i + 1}" if i + 1 < len(self.pages) else None
        return {"items": self.pages[i], "next": nxt}

    def playlist(self, playlist_id, fields=None):
        assert playlist_id == PID
        return {"name": self.name, "tracks": self._page(0)}

    def next(self, page):
        i = int(page["next"].removeprefix("page"))
        return self._page(i)


def test_parse_playlist_id_url_uri_and_bare():
    assert parse_playlist_id(f"https://open.spotify.com/playlist/{PID}?si=abc") == PID
    assert parse_playlist_id(f"spotify:playlist:{PID}") == PID
    assert parse_playlist_id(PID) == PID


def test_parse_playlist_id_invalid_raises():
    with pytest.raises(ValueError):
        parse_playlist_id("https://example.com/not-a-playlist")


def test_fetch_maps_fields():
    name, tracks = fetch_playlist(FakeClient([[make_item(1)]]), PID)
    t = tracks[0]
    assert name == "My List"
    assert (t.position, t.title, t.artists, t.album) == (1, "Song 1", ["A", "B"], "Album")
    assert (t.duration_ms, t.isrc, t.year, t.explicit) == (180001, "ISRC1", 2021, True)
    assert t.cover_url == "http://img/big"


def test_fetch_skips_none_local_and_episode_items_but_keeps_positions():
    items = [
        make_item(1),
        {"track": None, "is_local": False},
        make_item(3, is_local=True),
        make_item(4, type="episode"),
        make_item(5),
    ]
    _, tracks = fetch_playlist(FakeClient([items]), PID)
    assert len(tracks) == 5
    assert [t is None for t in tracks] == [False, True, True, True, False]
    assert tracks[4].position == 5


def test_fetch_paginates_over_100():
    page1 = [make_item(i) for i in range(1, 101)]
    page2 = [make_item(i) for i in range(101, 151)]
    _, tracks = fetch_playlist(FakeClient([page1, page2]), PID)
    assert len(tracks) == 150
    assert [t.position for t in tracks] == list(range(1, 151))


def test_fetch_handles_missing_optional_fields():
    item = make_item(1, external_ids={}, album={"name": "A", "release_date": "", "images": []})
    _, tracks = fetch_playlist(FakeClient([[item]]), PID)
    t = tracks[0]
    assert (t.isrc, t.year, t.cover_url) == (None, None, None)
