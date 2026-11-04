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


def test_fetch_accepts_renamed_items_shape():
    class NewShapeClient:
        def playlist(self, playlist_id, fields=None):
            item = make_item(1)
            return {"name": "New", "items": {"items": [{"item": item["track"], "is_local": False}], "next": None}}

        def next(self, page):
            raise AssertionError("no next page")

    name, tracks = fetch_playlist(NewShapeClient(), PID)
    assert name == "New" and tracks[0].title == "Song 1"


def test_fetch_unknown_response_shape_raises_loudly():
    class Odd:
        def playlist(self, playlist_id, fields=None):
            return {"name": "x", "weird": {}}

    with pytest.raises(RuntimeError):
        fetch_playlist(Odd(), PID)


# ---- public playlists via the embed page ----
import json as _json

import spotipy as _spotipy

from playlist_download.spotify import PlaylistUnavailable, fetch_playlist_any, parse_embed_html


def embed_html(track_list, name="Public List", wrap=True):
    entity = {"name": name, "title": name, "trackList": track_list}
    data = {"props": {"pageProps": {"state": {"data": {"entity": entity}}}}}
    body = _json.dumps(data, ensure_ascii=False)
    return f'<html><script id="__NEXT_DATA__" type="application/json">{body}</script></html>' if wrap else body


def embed_track(n, **kw):
    t = {"uri": f"spotify:track:{n:022d}", "title": f"Song {n}", "subtitle": "Artist A, Artist B",
         "isExplicit": n % 2 == 0, "duration": 200000 + n, "entityType": "track"}
    t.update(kw)
    return t


def test_parse_embed_maps_tracks_and_splits_artists():
    name, tracks = parse_embed_html(embed_html([embed_track(1), embed_track(2)]))
    assert name == "Public List"
    t = tracks[0]
    assert (t.position, t.title, t.artists, t.duration_ms) == (1, "Song 1", ["Artist A", "Artist B"], 200001)
    assert (t.album, t.isrc, t.year, t.cover_url, t.explicit) == ("", None, None, None, False)
    assert tracks[1].explicit is True


def test_parse_embed_keeps_positions_for_unusable_items():
    items = [embed_track(1), embed_track(2, uri="spotify:episode:abc", entityType="episode"), embed_track(3)]
    _, tracks = parse_embed_html(embed_html(items))
    assert [t is None for t in tracks] == [False, True, False]
    assert tracks[2].position == 3


def test_parse_embed_unicode_titles_survive():
    _, tracks = parse_embed_html(embed_html([embed_track(1, title="Море 🎵", subtitle="Скрябін")]))
    assert tracks[0].title == "Море 🎵" and tracks[0].artists == ["Скрябін"]


@pytest.mark.parametrize("html", ["<html>nothing here</html>", embed_html([], wrap=True).replace("trackList", "other"),
                                  '<script id="__NEXT_DATA__" type="application/json">{not json</script>'])
def test_parse_embed_unexpected_page_raises(html):
    with pytest.raises(PlaylistUnavailable):
        parse_embed_html(html)


def official_ok(client, pid):
    return "Mine", [make_item_track(1)]


def make_item_track(n):
    from playlist_download.models import Track
    return Track(n, f"Official {n}", ["A"], "Album", 1000, "ISRC", 2020, False, "http://c")


def embed_ok(pid):
    return "Public", [make_item_track(1)]


def spotify_error(status):
    return _spotipy.SpotifyException(status, -1, "nope")


def test_any_uses_official_when_logged_in_and_allowed():
    calls = []
    name, tracks, notice = fetch_playlist_any(object(), PID, fetch_official=official_ok,
                                              fetch_embed=lambda p: calls.append(p) or embed_ok(p))
    assert (name, notice, calls) == ("Mine", "", [])


@pytest.mark.parametrize("status", [401, 403, 404])
def test_any_falls_back_to_embed_when_spotify_refuses(status):
    def refuse(client, pid):
        raise spotify_error(status)

    name, tracks, notice = fetch_playlist_any(object(), PID, fetch_official=refuse, fetch_embed=embed_ok)
    assert name == "Public" and "public playlist page" in notice


def test_any_falls_back_when_response_has_no_track_list():
    def no_tracks(client, pid):
        raise RuntimeError("Unexpected Spotify response")

    assert fetch_playlist_any(object(), PID, fetch_official=no_tracks, fetch_embed=embed_ok)[0] == "Public"


def test_any_other_spotify_errors_are_not_swallowed():
    def rate_limited(client, pid):
        raise spotify_error(429)

    with pytest.raises(_spotipy.SpotifyException):
        fetch_playlist_any(object(), PID, fetch_official=rate_limited, fetch_embed=embed_ok)


def test_any_without_login_goes_straight_to_embed():
    def must_not_run(client, pid):
        raise AssertionError("official called without a client")

    assert fetch_playlist_any(None, PID, fetch_official=must_not_run, fetch_embed=embed_ok)[0] == "Public"


def test_any_embed_failure_without_login_asks_to_connect():
    def broken(pid):
        raise PlaylistUnavailable("page gone")

    with pytest.raises(PlaylistUnavailable, match="(?i)connect spotify"):
        fetch_playlist_any(None, PID, fetch_embed=broken)


def test_any_embed_failure_with_login_explains_ownership_rule():
    def refuse(client, pid):
        raise spotify_error(403)

    def broken(pid):
        raise PlaylistUnavailable("page gone")

    with pytest.raises(PlaylistUnavailable, match="own or collaborate"):
        fetch_playlist_any(object(), PID, fetch_official=refuse, fetch_embed=broken)


def test_any_warns_when_embed_list_may_be_truncated():
    def full(pid):
        return "Big", [make_item_track(i) for i in range(1, 101)]

    notice = fetch_playlist_any(None, PID, fetch_embed=full)[2]
    assert "first 100" in notice
