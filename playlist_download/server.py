import html
import json
import os
import re
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from playlist_download.archive import write_archive
from playlist_download.jobs import JobManager, ResolveError
from playlist_download.naming import sanitize

STATIC_DIR = Path(__file__).parent / "static"
MAX_BODY = 64 * 1024
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
_JOB_ROUTE = re.compile(r"^/api/jobs/([^/]+)(/resolve|/archive)?$")


class AppContext:
    def __init__(self, manager: JobManager, auth, extra_hosts=()):
        self.manager = manager
        self.auth = auth
        env_hosts = [h.strip() for h in os.environ.get("WEB_ALLOWED_HOSTS", "").split(",") if h.strip()]
        self.allowed_hosts = LOCAL_HOSTS | set(extra_hosts) | set(env_hosts)


def _hostname(host_header: str) -> str:
    if host_header.startswith("["):
        return host_header.split("]")[0] + "]"
    return host_header.split(":")[0]


def _page(title: str, message: str) -> bytes:
    return (f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title>"
            f"<body style='font-family:sans-serif;padding:2rem'><h1>{html.escape(title)}</h1>"
            f"<p>{html.escape(message)}</p><p><a href='/'>Back</a></p>").encode()


def make_handler(ctx: AppContext):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PlaylistDL"

        def log_message(self, fmt, *args):  # polling would flood the console
            pass

        # ---- response helpers
        def _send(self, status, payload: bytes, content_type: str, headers: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj).encode(), "application/json")

        def _error(self, status, message):
            self._json(status, {"error": message})

        # ---- guards
        def _host_ok(self) -> bool:
            if _hostname(self.headers.get("Host", "")) in ctx.allowed_hosts:
                return True
            self._error(403, "Unexpected Host header.")
            return False

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is None or urlparse(origin).netloc == self.headers.get("Host"):
                return True
            self._error(403, "Cross-origin request refused.")
            return False

        def _body(self) -> dict | None:
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._error(415, "Send application/json.")
                return None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise ValueError
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError
                return data
            except ValueError:
                self._error(400, "Invalid JSON body.")
                return None

        # ---- GET
        def do_GET(self):
            if not self._host_ok():
                return
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                self._send(200, (STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
            elif path == "/api/auth":
                self._auth_status()
            elif path == "/callback":
                self._callback(parse_qs(parsed.query))
            else:
                m = _JOB_ROUTE.match(path)
                if m and m.group(2) is None:
                    self._job_state(m.group(1))
                elif m and m.group(2) == "/archive":
                    self._archive(m.group(1))
                else:
                    self._error(404, "Not found.")

        def _auth_status(self):
            if ctx.auth.connected():
                self._json(200, {"connected": True})
            else:
                self._json(200, {"connected": False, "login_url": ctx.auth.login_url()})

        def _callback(self, query):
            if "error" in query:
                self._send(400, _page("Spotify login failed", query["error"][0]), "text/html; charset=utf-8")
                return
            code = (query.get("code") or [""])[0]
            if not code:
                self._send(400, _page("Spotify login failed", "No authorization code received."),
                           "text/html; charset=utf-8")
                return
            try:
                ctx.auth.finish(code)
            except Exception as exc:
                self._send(502, _page("Spotify login failed", str(exc)), "text/html; charset=utf-8")
                return
            self._send(302, b"", "text/plain", {"Location": "/"})

        def _job_state(self, job_id):
            job = ctx.manager.get(job_id)
            if job is None:
                self._error(404, "Unknown job.")
            else:
                self._json(200, ctx.manager.snapshot(job))

        def _archive(self, job_id):
            job = ctx.manager.get(job_id)
            if job is None:
                self._error(404, "Unknown job.")
                return
            if job.out_dir is None or not job.out_dir.is_dir():
                self._error(404, "Nothing to download yet.")
                return
            with tempfile.TemporaryFile() as tmp:
                if write_archive(job.out_dir, tmp) == 0:
                    self._error(404, "No finished songs yet.")
                    return
                size = tmp.tell()
                tmp.seek(0)
                name = f"{sanitize(job.name or 'playlist')}.zip"
                ascii_name = name.encode("ascii", "ignore").decode() or "playlist.zip"
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition",
                                 f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}")
                self.end_headers()
                while chunk := tmp.read(1 << 20):
                    self.wfile.write(chunk)

        # ---- POST
        def do_POST(self):
            if not (self._host_ok() and self._origin_ok()):
                return
            path = urlparse(self.path).path
            if path == "/api/jobs":
                body = self._body()
                if body is not None:
                    self._start_job(body)
                return
            m = _JOB_ROUTE.match(path)
            if m and m.group(2) == "/resolve":
                body = self._body()
                if body is not None:
                    self._resolve(m.group(1), body)
                return
            self._error(404, "Not found.")

        def _start_job(self, body):
            if not ctx.auth.connected():
                self._error(401, "Connect Spotify first.")
                return
            url, threshold = body.get("url"), body.get("threshold", 70.0)
            if not isinstance(url, str) or not url.strip():
                self._error(400, "Paste a Spotify playlist link.")
                return
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
                self._error(400, "threshold must be a number.")
                return
            try:
                job = ctx.manager.start(url.strip(), float(threshold))
            except ValueError as exc:
                self._error(400, str(exc))
            except RuntimeError as exc:
                self._error(409, str(exc))
            else:
                self._json(202, {"id": job.id})

        def _resolve(self, job_id, body):
            position, action = body.get("position"), body.get("action")
            index, url = body.get("candidate_index"), body.get("url")
            if isinstance(position, bool) or not isinstance(position, int) or not isinstance(action, str):
                self._error(400, "position (integer) and action are required.")
                return
            if url is not None and not isinstance(url, str):
                self._error(400, "url must be text.")
                return
            try:
                snap = ctx.manager.resolve(job_id, position, action, candidate_index=index, url=url)
            except KeyError:
                self._error(404, "Unknown job.")
            except ValueError as exc:
                self._error(400, str(exc))
            except ResolveError as exc:
                self._error(502, str(exc))
            else:
                self._json(200, snap)

    return Handler


def create_server(ctx: AppContext, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(ctx))
    server.daemon_threads = True
    return server
