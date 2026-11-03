import argparse
import os
import sys
from pathlib import Path

from playlist_download.config import ConfigError, check_ffmpeg, load_config
from playlist_download.downloader import DownloadError, download_audio, fetch_cover, tag_file
from playlist_download.matcher import pick_best, rank_candidates
from playlist_download.naming import find_existing, sanitize, track_filename
from playlist_download.report import TrackResult, format_failed, summary, write_reports
from playlist_download.spotify import fetch_playlist, make_client, parse_playlist_id

DEFAULT_THRESHOLD = 70.0


def _cleanup_partials(out_dir: Path, position: int, width: int) -> None:
    for leftover in out_dir.glob(f".{position:0{width}d}.part*"):
        leftover.unlink(missing_ok=True)


def process_track(track, position, width, out_dir, threshold, rank=rank_candidates,
                  download=download_audio, tag=tag_file, cover=fetch_cover) -> TrackResult:
    if track is None:
        return TrackResult(position, None, "failed", None, [], "unavailable track")
    out_dir.mkdir(parents=True, exist_ok=True)
    if find_existing(out_dir, position, width):
        return TrackResult(position, track, "skipped_existing", None, [], None)
    try:
        ranked = rank(track)
    except Exception as exc:
        return TrackResult(position, track, "failed", None, [], f"search error: {exc}")
    best = pick_best(ranked, threshold)
    if best is None:
        return TrackResult(position, track, "failed", None, ranked, "no match above threshold")

    temp = out_dir / f".{position:0{width}d}.part.mp3"
    final = out_dir / track_filename(track, width)
    try:
        try:
            download(best.url, temp)
        except DownloadError as exc:
            return TrackResult(position, track, "failed", best, ranked, f"download error: {exc}")
        try:
            tag(temp, track, cover(track.cover_url))
        except Exception as exc:
            return TrackResult(position, track, "failed", best, ranked, f"tagging error: {exc}")
        os.replace(temp, final)
        return TrackResult(position, track, "downloaded", best, ranked, None)
    finally:
        _cleanup_partials(out_dir, position, width)


def _label(result: TrackResult) -> str:
    if result.track is None:
        return "(unavailable track)"
    return f"{', '.join(result.track.artists)} - {result.track.title}"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Download a Spotify playlist's songs as tagged mp3 files.")
    parser.add_argument("playlist", help="Spotify playlist URL, URI or id")
    parser.add_argument("--out", default="downloads", help="output base directory (default: downloads)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"minimum match score 0-100 (default: {DEFAULT_THRESHOLD:g})")
    args = parser.parse_args(argv)

    try:
        playlist_id = parse_playlist_id(args.playlist)
        check_ffmpeg()
        config = load_config()
    except (ValueError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        name, tracks = fetch_playlist(make_client(config), playlist_id)
    except Exception as exc:
        print(f"Spotify error: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out) / sanitize(name)
    width = len(str(len(tracks)))
    print(f"Playlist '{name}': {len(tracks)} tracks -> {out_dir}")
    results: list[TrackResult] = []
    for i, track in enumerate(tracks, start=1):
        result = process_track(track, i, width, out_dir, args.threshold)
        results.append(result)
        print(f"[{i}/{len(tracks)}] {result.status:<16} {_label(result)}"
              + (f"  ({result.reason})" if result.reason else ""))

    write_reports(out_dir, results)
    print(f"\n{summary(results)}")
    failed = format_failed(results)
    if failed:
        print("\nNot downloaded:\n" + failed)
    print(f"\nReports: {out_dir / 'failed.txt'}, {out_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
