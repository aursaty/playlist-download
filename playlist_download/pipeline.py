import os
from pathlib import Path
from typing import Callable, Iterator

from playlist_download.downloader import DownloadError, download_audio, fetch_cover, tag_file
from playlist_download.matcher import pick_best, rank_candidates
from playlist_download.models import Track
from playlist_download.naming import MAX_STEM, track_filename
from playlist_download.report import TrackResult

MAX_PATH = 255
MIN_STEM = 40


class TagError(Exception):
    pass


def cleanup_partials(out_dir: Path, position: int, width: int) -> None:
    for leftover in out_dir.glob(f".{position:0{width}d}.part*"):
        leftover.unlink(missing_ok=True)


def final_path(track: Track, width: int, out_dir: Path) -> Path:
    room = MAX_PATH - len(str(out_dir.resolve())) - len(os.sep) - len(".mp3")
    return out_dir / track_filename(track, width, max_stem=max(MIN_STEM, min(MAX_STEM, room)))


def place_download(track: Track, url: str, width: int, out_dir: Path, download=download_audio,
                   tag=tag_file, cover=fetch_cover) -> Path:
    """Download `url`, tag it and move it to the track's final name. Raises DownloadError, TagError or OSError."""
    out_dir.mkdir(parents=True, exist_ok=True)
    temp = out_dir / f".{track.position:0{width}d}.part.mp3"
    final = final_path(track, width, out_dir)
    try:
        download(url, temp)
        try:
            tag(temp, track, cover(track.cover_url))
        except Exception as exc:
            raise TagError(str(exc)) from exc
        os.replace(temp, final)
        return final
    finally:
        cleanup_partials(out_dir, track.position, width)


def process_track(track, position, width, out_dir, threshold, rank=rank_candidates,
                  download=download_audio, tag=tag_file, cover=fetch_cover) -> TrackResult:
    if track is None:
        return TrackResult(position, None, "failed", None, [], "unavailable track")
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        if final_path(track, width, out_dir).exists():
            return TrackResult(position, track, "skipped_existing", None, [], None)
    except OSError as exc:
        return TrackResult(position, track, "failed", None, [], f"file error: {exc}")
    try:
        ranked = rank(track)
    except Exception as exc:
        return TrackResult(position, track, "failed", None, [], f"search error: {exc}")
    best = pick_best(ranked, threshold)
    if best is None:
        return TrackResult(position, track, "failed", None, ranked, "no match above threshold")
    try:
        place_download(track, best.url, width, out_dir, download, tag, cover)
    except DownloadError as exc:
        return TrackResult(position, track, "failed", best, ranked, f"download error: {exc}")
    except TagError as exc:
        return TrackResult(position, track, "failed", best, ranked, f"tagging error: {exc}")
    except OSError as exc:
        return TrackResult(position, track, "failed", best, ranked, f"file error: {exc}")
    return TrackResult(position, track, "downloaded", best, ranked, None)


def iter_pipeline(tracks: list, out_dir: Path, threshold: float,
                  process: Callable = process_track) -> Iterator[TrackResult]:
    """Yield one result per track in playlist order. One bad track never stops the run."""
    width = len(str(len(tracks)))
    for i, track in enumerate(tracks, start=1):
        try:
            yield process(track, i, width, out_dir, threshold)
        except Exception as exc:
            yield TrackResult(i, track, "failed", None, [], f"unexpected error: {exc}")
