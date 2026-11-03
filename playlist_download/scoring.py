import re

from rapidfuzz import fuzz

from playlist_download.models import Candidate, Track

PENALTY_WORDS = ["live", "cover", "remix", "karaoke", "sped up", "slowed", "reverb", "lyrics", "instrumental"]
PENALTY = 40  # a single penalty word must sink an otherwise perfect match below threshold 70
VERSION_MISMATCH_PENALTY = 30
EXTRA_WORDS_PENALTY = 30
EXTRA_WORDS_ALLOWED = 2
NO_ARTIST_CAP = 69  # artist mismatch is the main wrong-song risk: never reaches threshold 70
NOISE_WORDS = {"official", "audio", "video", "lyric", "lyrics", "hd", "hq", "topic", "music", "visualizer",
               "ft", "feat", "featuring", "remastered", "remaster"}

_BRACKETS = re.compile(r"\(([^)]*)\)|\[([^\]]*)\]")
_FEAT = re.compile(r"\b(feat|ft)\.?\s.*$")
_PUNCT = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")
_FEAT_TAG = re.compile(r"^(feat|ft|with|featuring)\b")


def _clean(text: str) -> str:
    return _SPACES.sub(" ", _PUNCT.sub(" ", text)).strip()


def normalize(text: str) -> str:
    base = text.casefold().strip()
    out = _BRACKETS.sub(" ", base)
    out = _FEAT.sub(" ", out)
    out = _clean(out)
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
        if name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", haystack):
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


def _version_tags(title: str) -> list[str]:
    tags = []
    for m in _BRACKETS.finditer(title.casefold()):
        tag = _clean(m.group(1) or m.group(2) or "")
        if tag and not _FEAT_TAG.match(tag):
            tags.append(tag)
    return tags


def _version_penalty(track: Track, cand: Candidate) -> float:
    cand_text = _clean(cand.title.casefold())
    if any(tag not in cand_text for tag in _version_tags(track.title)):
        return VERSION_MISMATCH_PENALTY
    return 0.0


def _extra_words_penalty(track: Track, cand: Candidate) -> float:
    known = set(normalize(track.title).split())
    for artist in track.artists:
        known.update(normalize(artist).split())
    extra = [w for w in normalize(cand.title).split() if w not in known and w not in NOISE_WORDS]
    return EXTRA_WORDS_PENALTY if len(extra) > EXTRA_WORDS_ALLOWED else 0.0


def score_candidate(track: Track, cand: Candidate) -> float:
    title = fuzz.token_set_ratio(normalize(track.title), normalize(cand.title)) / 100 * 30
    artist = _artist_points(track, cand)
    score = _duration_points(track, cand) + title + artist + _bonus_points(track, cand)
    score -= _penalty_points(track, cand) + _version_penalty(track, cand) + _extra_words_penalty(track, cand)
    if artist == 0:
        score = min(score, NO_ARTIST_CAP)
    return max(0.0, min(100.0, score))
