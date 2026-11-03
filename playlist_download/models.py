from dataclasses import dataclass


@dataclass
class Track:
    position: int
    title: str
    artists: list[str]
    album: str
    duration_ms: int
    isrc: str | None
    year: int | None
    explicit: bool
    cover_url: str | None


@dataclass
class Candidate:
    url: str
    source: str  # "ytmusic" or "youtube"
    title: str
    channel: str
    duration_s: int | None
    album: str | None
    score: float = 0.0
