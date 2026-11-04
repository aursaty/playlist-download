import re

from rapidfuzz import fuzz

from playlist_download.models import Candidate, Track
from playlist_download.translit import phonetic_key

PENALTY_WORDS = ["live", "cover", "remix", "mix", "karaoke", "sped up", "slowed", "reverb", "lyrics", "instrumental"]
PENALTY = 40  # a single penalty word must sink an otherwise perfect match below threshold 70
VERSION_MISMATCH_PENALTY = 30
EXTRA_WORDS_PENALTY = 30
EXTRA_WORDS_ALLOWED = 2
NO_ARTIST_CAP = 69  # artist mismatch is the main wrong-song risk: never reaches threshold 70
TITLE_FLOOR = 50  # title similarity (0-100) below this can never reach threshold 70
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
    key_haystack = f"{phonetic_key(cand.channel)} {phonetic_key(cand.title)}"
    best = 0.0
    for i, artist in enumerate(track.artists):
        points = 20.0 if i == 0 else 10.0
        name, key = normalize(artist), phonetic_key(artist)
        if name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", haystack):
            best = max(best, points)
        elif key and re.search(rf"(?<!\w){re.escape(key)}(?!\w)", key_haystack):
            best = max(best, points)
    return best


def _bonus_points(track: Track, cand: Candidate) -> float:
    pts = 0.0
    channel = cand.channel.casefold().strip()
    artists = {normalize(a) for a in track.artists}
    artist_keys = {phonetic_key(a) for a in track.artists}
    if channel.endswith("- topic") or normalize(cand.channel) in artists or phonetic_key(cand.channel) in artist_keys:
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
    known = set(phonetic_key(normalize(track.title)).split())
    for artist in track.artists:
        known.update(phonetic_key(artist).split())
    noise = {phonetic_key(w) for w in NOISE_WORDS}
    extra = [w for w in phonetic_key(normalize(cand.title)).split() if w not in known and w not in noise]
    return EXTRA_WORDS_PENALTY if len(extra) > EXTRA_WORDS_ALLOWED else 0.0


def _title_similarity(track: Track, cand: Candidate) -> float:
    a, b = normalize(track.title), normalize(cand.title)
    return max(fuzz.token_set_ratio(a, b), fuzz.token_set_ratio(phonetic_key(a), phonetic_key(b)))


def score_candidate(track: Track, cand: Candidate) -> float:
    similarity = _title_similarity(track, cand)
    artist = _artist_points(track, cand)
    score = _duration_points(track, cand) + similarity / 100 * 30 + artist + _bonus_points(track, cand)
    score -= _penalty_points(track, cand) + _version_penalty(track, cand) + _extra_words_penalty(track, cand)
    if artist == 0 or similarity < TITLE_FLOOR:
        score = min(score, NO_ARTIST_CAP)
    return max(0.0, min(100.0, score))
