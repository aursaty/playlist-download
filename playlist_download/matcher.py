import logging
from typing import Callable
from urllib.parse import parse_qs, urlparse

from playlist_download.models import Candidate, Track
from playlist_download.scoring import score_candidate

log = logging.getLogger(__name__)

Searcher = Callable[[str], list[Candidate]]
RESULTS_PER_QUERY = 5

_ytmusic = None


def ytmusic_result_to_candidate(result: dict) -> Candidate | None:
    video_id = result.get("videoId")
    if not video_id:
        return None
    album = result.get("album") or {}
    artists = result.get("artists") or []
    return Candidate(
        url=f"https://music.youtube.com/watch?v={video_id}",
        source="ytmusic",
        title=result.get("title", ""),
        channel=", ".join(a["name"] for a in artists if a.get("name")),
        duration_s=result.get("duration_seconds"),
        album=album.get("name"),
    )


def youtube_entry_to_candidate(entry: dict) -> Candidate | None:
    video_id = entry.get("id")
    if not video_id:
        return None
    duration = entry.get("duration")
    return Candidate(
        url=f"https://www.youtube.com/watch?v={video_id}",
        source="youtube",
        title=entry.get("title", ""),
        channel=entry.get("channel") or entry.get("uploader") or "",
        duration_s=int(duration) if duration else None,
        album=None,
    )


def search_ytmusic(query: str) -> list[Candidate]:
    global _ytmusic
    if _ytmusic is None:
        from ytmusicapi import YTMusic

        _ytmusic = YTMusic()
    results = _ytmusic.search(query, filter="songs", limit=RESULTS_PER_QUERY)
    return [c for r in results if (c := ytmusic_result_to_candidate(r))]


def search_youtube(query: str) -> list[Candidate]:
    from yt_dlp import YoutubeDL

    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{RESULTS_PER_QUERY}:{query}", download=False)
    return [c for e in info.get("entries", []) if e and (c := youtube_entry_to_candidate(e))]


def _video_id(url: str) -> str:
    return parse_qs(urlparse(url).query).get("v", [url])[0]


def _plan(track: Track) -> list[tuple[Searcher, list[str]]]:
    base = f"{track.artists[0] if track.artists else ''} {track.title}".strip()
    return [
        (search_ytmusic, [base]),
        (search_youtube, [base, f"{base} official audio", f"{base} topic"]),
    ]


def rank_candidates(track: Track, searchers: list[Searcher] | None = None) -> list[Candidate]:
    base = f"{track.artists[0] if track.artists else ''} {track.title}".strip()
    plan = _plan(track) if searchers is None else [(s, [base]) for s in searchers]
    best: dict[str, Candidate] = {}
    for search, queries in plan:
        for query in queries:
            try:
                found = search(query)
            except Exception as exc:  # one failing source must not stop the others
                log.warning("search failed for %r: %s", query, exc)
                continue
            for cand in found:
                cand.score = score_candidate(track, cand)
                vid = _video_id(cand.url)
                if vid not in best or cand.score > best[vid].score:
                    best[vid] = cand
    return sorted(best.values(), key=lambda c: c.score, reverse=True)


def pick_best(ranked: list[Candidate], threshold: float = 70) -> Candidate | None:
    if ranked and ranked[0].score >= threshold:
        return ranked[0]
    return None
