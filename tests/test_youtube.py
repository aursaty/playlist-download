import pytest

from playlist_download.youtube import is_youtube_url, youtube_id


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abc123DEF_-", "abc123DEF_-"),
    ("https://music.youtube.com/watch?v=abc123DEF_-&list=x", "abc123DEF_-"),
    ("https://youtu.be/abc123DEF_-?t=5", "abc123DEF_-"),
    ("https://www.youtube.com/shorts/abc123DEF_-", "abc123DEF_-"),
    ("https://example.com/watch?v=abc", None),
    ("not a url", None),
])
def test_youtube_id(url, expected):
    assert youtube_id(url) == expected


@pytest.mark.parametrize("url,ok", [
    ("https://www.youtube.com/watch?v=abc123DEF_-", True),
    ("https://youtu.be/abc123DEF_-", True),
    ("http://music.youtube.com/watch?v=abc123DEF_-", True),
    ("https://evil.com/watch?v=abc123DEF_-", False),
    ("https://youtube.com.evil.com/watch?v=abc123DEF_-", False),
    ("javascript:alert(1)", False),
    ("https://www.youtube.com/", False),
])
def test_is_youtube_url(url, ok):
    assert is_youtube_url(url) is ok
