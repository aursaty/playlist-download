import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playlist_download.config import ConfigError, check_ffmpeg, load_config
from playlist_download.jobs import JobManager
from playlist_download.server import AppContext, create_server
from playlist_download.webauth import WebAuth


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Run the playlist downloader web app.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                        help="interface to bind (default 127.0.0.1; use 0.0.0.0 inside Docker)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--out", default=os.environ.get("DOWNLOAD_DIR", "downloads"), help="download folder")
    parser.add_argument("--cache", default=os.environ.get("SPOTIFY_CACHE_PATH", ".cache-web"),
                        help="where the Spotify login token is stored")
    args = parser.parse_args(argv)

    try:
        check_ffmpeg()
        config = load_config()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    redirect_port = urlparse(config.web_redirect_uri).port
    if redirect_port is not None and redirect_port != args.port:
        print(f"warning: WEB_REDIRECT_URI uses port {redirect_port} but the server listens on {args.port}; "
              "the Spotify login will not come back to this app.", file=sys.stderr)

    auth = WebAuth(config, Path(args.cache))
    manager = JobManager(Path(args.out), lambda: auth.client() if auth.connected() else None)
    server = create_server(AppContext(manager, auth), args.host, args.port)
    print(f"vibedl is running: http://127.0.0.1:{args.port}")
    print(f"Spotify redirect URI to register: {config.web_redirect_uri}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
