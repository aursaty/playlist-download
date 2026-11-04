import http.client
import io
import json
import threading
import time
import zipfile

import pytest

from playlist_download.jobs import JobManager
from playlist_download.models import Candidate, Track
from playlist_download.report import TrackResult
from playlist_download.server import AppContext, create_server

URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"


def make_track(position):
    return Track(position=position, title=f"Song {position}", artists=["Artist"], album="Album",
                 duration_ms=200000, isrc=None, year=2020, explicit=False, cover_url=None)


def cand(n):
    return Candidate(url=f"https://www.youtube.com/watch?v=vid{n:08d}", source="youtube", title=f"Cand {n}",
                     channel="Chan", duration_s=200, album=None, score=50.0)


def fake_fetch(client, pid):
    return "My List", [make_track(1), make_track(2)]


def fake_process(track, position, width, out_dir, threshold):
    out_dir.mkdir(parents=True, exist_ok=True)
    if position == 1:
        (out_dir / "1 - Artist - Song 1.mp3").write_bytes(b"audio1")
        return TrackResult(position, track, "downloaded", cand(0), [cand(0)], None)
    return TrackResult(position, track, "failed", None, [cand(1), cand(2)], "no match above threshold")


def fake_place(track, url, width, out_dir):
    path = out_dir / f"{track.position} - Artist - {track.title}.mp3"
    path.write_bytes(b"audio2")
    return path


class FakeAuth:
    def __init__(self, connected=True):
        self._connected = connected
        self.codes = []

    def connected(self):
        return self._connected

    def login_url(self):
        return "https://accounts.spotify.com/authorize?x=1"

    def finish(self, code):
        self.codes.append(code)
        self._connected = True

    def client(self):
        return object()


@pytest.fixture
def env(tmp_path):
    auth = FakeAuth()
    mgr = JobManager(tmp_path, auth.client, process=fake_process, fetch=fake_fetch, place=fake_place)
    server = create_server(AppContext(mgr, auth), "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield {"host": host, "port": port, "auth": auth, "mgr": mgr}
    server.shutdown()
    server.server_close()


def call(env, method, path, body=None, headers=None, raw=None):
    conn = http.client.HTTPConnection(env["host"], env["port"], timeout=10)
    hdrs = dict(headers or {})
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), payload


def call_json(env, method, path, body=None, headers=None):
    status, hdrs, payload = call(env, method, path, body, headers)
    return status, json.loads(payload) if payload else None


def wait_for(env, job_id, states=("review", "done", "error")):
    for _ in range(100):
        status, snap = call_json(env, "GET", f"/api/jobs/{job_id}")
        if snap["status"] in states:
            return snap
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_index_page_is_served(env):
    status, hdrs, payload = call(env, "GET", "/")
    assert status == 200 and hdrs["Content-Type"].startswith("text/html")
    assert payload.lower().startswith(b"<!doctype html")


def test_unknown_path_is_404_and_traversal_is_not_served(env):
    assert call(env, "GET", "/nope")[0] == 404
    assert call(env, "GET", "/static/../server.py")[0] == 404
    assert call(env, "GET", "/..%2fserver.py")[0] == 404


def test_auth_status_when_connected_and_not(env):
    assert call_json(env, "GET", "/api/auth")[1] == {"connected": True}
    env["auth"]._connected = False
    assert call_json(env, "GET", "/api/auth")[1] == {"connected": False, "login_url": "https://accounts.spotify.com/authorize?x=1"}


def test_callback_exchanges_code_and_redirects_home(env):
    env["auth"]._connected = False
    status, hdrs, _ = call(env, "GET", "/callback?code=abc123")
    assert status == 302 and hdrs["Location"] == "/"
    assert env["auth"].codes == ["abc123"]


def test_callback_error_shows_message(env):
    status, _, payload = call(env, "GET", "/callback?error=access_denied")
    assert status == 400 and b"access_denied" in payload


def test_start_works_without_spotify_login_for_public_playlists(env):
    env["auth"]._connected = False
    status, body = call_json(env, "POST", "/api/jobs", {"url": URL})
    assert status == 202
    assert wait_for(env, body["id"])["status"] in ("review", "done")


def test_full_cycle_start_review_resolve_archive(env):
    status, body = call_json(env, "POST", "/api/jobs", {"url": URL})
    assert status == 202
    job_id = body["id"]
    snap = wait_for(env, job_id)
    assert snap["status"] == "review" and [c["position"] for c in snap["review"]] == [2]

    status, snap = call_json(env, "POST", f"/api/jobs/{job_id}/resolve",
                             {"position": 2, "action": "accept", "candidate_index": 0})
    assert status == 200 and snap["status"] == "done" and snap["can_archive"] is True

    status, hdrs, payload = call(env, "GET", f"/api/jobs/{job_id}/archive")
    assert status == 200 and hdrs["Content-Type"] == "application/zip"
    assert "attachment" in hdrs["Content-Disposition"] and "My" in hdrs["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert sorted(z.namelist()) == ["My List/1 - Artist - Song 1.mp3", "My List/2 - Artist - Song 2.mp3"]


def test_start_validation_errors(env):
    assert call_json(env, "POST", "/api/jobs", {"url": "https://example.com/x"})[0] == 400
    assert call_json(env, "POST", "/api/jobs", {})[0] == 400
    assert call_json(env, "POST", "/api/jobs", {"url": URL, "threshold": "high"})[0] == 400
    assert call(env, "POST", "/api/jobs", raw=b"{not json", headers={"Content-Type": "application/json"})[0] == 400


def test_second_job_while_running_is_conflict(env):
    gate = threading.Event()
    original = env["mgr"].process

    def slow(*a, **k):
        gate.wait(5)
        return original(*a, **k)

    env["mgr"].process = slow
    first = call_json(env, "POST", "/api/jobs", {"url": URL})
    try:
        assert first[0] == 202
        assert call_json(env, "POST", "/api/jobs", {"url": URL})[0] == 409
    finally:
        gate.set()
        wait_for(env, first[1]["id"])


def test_resolve_errors(env):
    job_id = call_json(env, "POST", "/api/jobs", {"url": URL})[1]["id"]
    wait_for(env, job_id)
    assert call_json(env, "POST", "/api/jobs/nope/resolve", {"position": 2, "action": "skip"})[0] == 404
    assert call_json(env, "POST", f"/api/jobs/{job_id}/resolve", {"position": 1, "action": "skip"})[0] == 400
    assert call_json(env, "POST", f"/api/jobs/{job_id}/resolve", {"position": "x", "action": "skip"})[0] == 400
    assert call_json(env, "POST", f"/api/jobs/{job_id}/resolve",
                     {"position": 2, "action": "accept", "url": "https://evil.com/x"})[0] == 400


def test_unknown_job_is_404(env):
    assert call_json(env, "GET", "/api/jobs/nope")[0] == 404
    assert call(env, "GET", "/api/jobs/nope/archive")[0] == 404


def test_post_requires_json_content_type(env):
    status, _, _ = call(env, "POST", "/api/jobs", raw=b'{"url": "x"}', headers={"Content-Type": "text/plain"})
    assert status == 415


def test_foreign_origin_post_is_refused(env):
    status, _ = call_json(env, "POST", "/api/jobs", {"url": URL}, headers={"Origin": "https://evil.example"})
    assert status == 403


def test_unexpected_host_header_is_refused(env):
    status, _, _ = call(env, "GET", "/api/auth", headers={"Host": "evil.example"})
    assert status == 403


def test_same_origin_post_is_allowed(env):
    host = f"127.0.0.1:{env['port']}"
    status, _ = call_json(env, "POST", "/api/jobs", {"url": URL},
                          headers={"Origin": f"http://{host}", "Host": host})
    assert status == 202
