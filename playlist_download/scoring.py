import re

from rapidfuzz import fuzz

from playlist_download.models import Candidate, Track

PENALTY_WORDS = ["live", "cover", "remix", "karaoke", "sped up", "slowed", "reverb", "lyrics", "instrumental"]
PENALTY = 25
NO_ARTIST_CAP = 69  # artist mismatch is the main wrong-song risk: never reaches threshold 70

_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_FEAT = re.compile(r"\b(feat|ft)\.?\s.*$")
_PUNCT = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    base = text.casefold().strip()
    out = _BRACKETS.sub(" ", base)
    out = _FEAT.sub(" ", out)
    out = _PUNCT.sub(" ", out)
    out = _SPACES.sub(" ", out).strip()
    return out or base


def _duration_points(track: Track, cand: Candidate) -> float:
    if not cand.duration_s:
        return 0.0
    delta = abs(cand.duration_s - track.duration_ms / 1000)
    if delta <= 3:
        return 40.0
    if delta >= 15:
        return 0.0
    return 40.0 * (15 - delta) / 12


def _artist_points(track: Track, cand: Candidate) -> float:
    haystack = f"{normalize(cand.channel)} {normalize(cand.title)}"
    best = 0.0
    for i, artist in enumerate(track.artists):
        name = normalize(artist)
        if name and name in haystack:
            best = max(best, 20.0 if i == 0 else 10.0)
    return best


def _bonus_points(track: Track, cand: Candidate) -> float:
    pts = 0.0
    channel = cand.channel.casefold().strip()
    artists = {normalize(a) for a in track.artists}
    if channel.endswith("- topic") or normalize(cand.channel) in artists:
        pts += 6.0
    if cand.source == "ytmusic" and cand.album and normalize(cand.album) == normalize(track.album):
        pts += 4.0
    return pts


def _penalty_points(track: Track, cand: Candidate) -> float:
    spotify_title = track.title.casefold()
    cand_title = cand.title.casefold()
    hits = 0
    for word in PENALTY_WORDS:
        pattern = rf"\b{re.escape(word)}\b"
        if re.search(pattern, cand_title) and not re.search(pattern, spotify_title):
            hits += 1
    return hits * PENALTY


def score_candidate(track: Track, cand: Candidate) -> float:
    title = fuzz.token_set_ratio(normalize(track.title), normalize(cand.title)) / 100 * 30
    artist = _artist_points(track, cand)
    score = _duration_points(track, cand) + title + artist + _bonus_points(track, cand)
    score -= _penalty_points(track, cand)
    if artist == 0:
        score = min(score, NO_ARTIST_CAP)
    return max(0.0, min(100.0, score))
