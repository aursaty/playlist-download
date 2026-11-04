import argparse
import sys
from pathlib import Path

from playlist_download.config import ConfigError, check_ffmpeg, load_config
from playlist_download.naming import sanitize
from playlist_download.pipeline import iter_pipeline, process_track
from playlist_download.report import TrackResult, format_failed, summary, write_reports
from playlist_download.spotify import fetch_playlist, make_client, parse_playlist_id

DEFAULT_THRESHOLD = 70.0
MAX_FOLDER_NAME = 60


def playlist_folder(base: Path, name: str) -> Path:
    return base / sanitize(name)[:MAX_FOLDER_NAME].rstrip(". ")


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

    out_dir = playlist_folder(Path(args.out), name)
    print(f"Playlist '{name}': {len(tracks)} tracks -> {out_dir}")
    results: list[TrackResult] = []
    interrupted = False
    try:
        # process_track is looked up here at call time so tests can replace it
        for result in iter_pipeline(tracks, out_dir, args.threshold, process=process_track):
            results.append(result)
            print(f"[{result.position}/{len(tracks)}] {result.status:<16} {_label(result)}"
                  + (f"  ({result.reason})" if result.reason else ""))
    except KeyboardInterrupt:
        interrupted = True
        print("Interrupted: writing reports for tracks processed so far.")

    write_reports(out_dir, results)
    print(f"\n{summary(results)}")
    failed = format_failed(results)
    if failed:
        print("\nNot downloaded:\n" + failed)
    print(f"\nReports: {out_dir / 'failed.txt'}, {out_dir / 'report.json'}")
    return 130 if interrupted else 0


if __name__ == "__main__":
    sys.exit(main())
