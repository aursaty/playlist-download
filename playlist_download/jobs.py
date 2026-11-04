import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from playlist_download.downloader import DownloadError
from playlist_download.models import Candidate
from playlist_download.naming import playlist_folder
from playlist_download.pipeline import TagError, iter_pipeline, place_download, process_track
from playlist_download.report import TrackResult, summary, write_reports
from playlist_download.spotify import fetch_playlist, parse_playlist_id
from playlist_download.youtube import is_youtube_url, youtube_id

ACTIVE = ("starting", "running")


class ResolveError(Exception):
    """A manual resolution failed (download/tag/file error); the track stays unresolved."""


@dataclass
class Job:
    id: str
    url: str
    threshold: float
    status: str = "starting"  # starting | running | review | done | error
    name: str = ""
    out_dir: Path | None = None
    total: int = 0
    results: list[TrackResult] = field(default_factory=list)
    resolutions: dict[int, str] = field(default_factory=dict)  # position -> accepted | skipped
    busy: set[int] = field(default_factory=set)  # positions whose manual download is in flight
    error: str | None = None
    thread: threading.Thread | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)


class JobManager:
    def __init__(self, base_dir: Path, get_client: Callable, process=process_track, fetch=fetch_playlist,
                 place=place_download):
        self.base_dir = Path(base_dir)
        self.get_client = get_client
        self.process = process
        self.fetch = fetch
        self.place = place
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, url: str, threshold: float = 70.0, background: bool = True) -> Job:
        playlist_id = parse_playlist_id(url)
        if not 0 <= threshold <= 100:
            raise ValueError("threshold must be between 0 and 100")
        with self._lock:
            if any(j.status in ACTIVE for j in self.jobs.values()):
                raise RuntimeError("A playlist is already being processed. Wait for it to finish.")
            job = Job(id=uuid.uuid4().hex[:12], url=url, threshold=threshold)
            self.jobs[job.id] = job
        if background:
            job.thread = threading.Thread(target=self._run, args=(job, playlist_id), daemon=True)
            job.thread.start()
        else:
            self._run(job, playlist_id)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def _run(self, job: Job, playlist_id: str) -> None:
        try:
            with job.lock:
                job.status = "running"
            name, tracks = self.fetch(self.get_client(), playlist_id)
            out_dir = playlist_folder(self.base_dir, name)
            with job.lock:
                job.name, job.total, job.out_dir = name, len(tracks), out_dir
            for result in iter_pipeline(tracks, out_dir, job.threshold, process=self.process):
                with job.lock:
                    job.results.append(result)
            with job.lock:
                write_reports(out_dir, job.results)
                self._refresh_status(job)
        except Exception as exc:
            with job.lock:
                job.status, job.error = "error", str(exc)

    @staticmethod
    def _is_pending(job: Job, r: TrackResult) -> bool:
        return r.status == "failed" and r.track is not None and r.position not in job.resolutions

    def _refresh_status(self, job: Job) -> None:
        job.status = "review" if any(self._is_pending(job, r) for r in job.results) else "done"

    def resolve(self, job_id: str, position: int, action: str, candidate_index: int | None = None,
                url: str | None = None) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if action not in ("accept", "skip"):
            raise ValueError("action must be 'accept' or 'skip'")
        with job.lock:
            if job.status in ACTIVE or job.status == "error":
                raise ValueError("job is not ready for review")
            result = next((r for r in job.results if r.position == position), None)
            if result is None or result.track is None:
                raise ValueError("this track cannot be reviewed")
            if result.status == "downloaded":
                raise ValueError("this track is already downloaded")
            if position in job.busy:
                raise ValueError("this track is already being processed")
            if action == "skip":
                job.resolutions[position] = "skipped"
                self._save(job)
                return self.snapshot(job)
            chosen = self._pick_candidate(result, candidate_index, url)
            job.busy.add(position)
        try:
            # the download runs without the lock so status polling stays responsive
            self._download(job, result, chosen)
        finally:
            with job.lock:
                job.busy.discard(position)
        with job.lock:
            result.status, result.chosen, result.reason = "downloaded", chosen, None
            job.resolutions[position] = "accepted"
            self._save(job)
        return self.snapshot(job)

    def _save(self, job: Job) -> None:
        write_reports(job.out_dir, job.results)
        self._refresh_status(job)

    @staticmethod
    def _pick_candidate(result: TrackResult, index: int | None, url: str | None) -> Candidate:
        if url:
            if not is_youtube_url(url):
                raise ValueError("paste a YouTube or YouTube Music link")
            return Candidate(url=url, source="manual", title="Manual link", channel="", duration_s=None, album=None)
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(result.candidates):
            raise ValueError("choose one of the candidates or paste a link")
        return result.candidates[index]

    def _download(self, job: Job, result: TrackResult, chosen: Candidate) -> None:
        try:
            self.place(result.track, chosen.url, len(str(job.total)), job.out_dir)
        except (DownloadError, TagError, OSError) as exc:
            raise ResolveError(f"download failed: {exc}") from exc

    def snapshot(self, job: Job) -> dict:
        with job.lock:
            items, review = [], []
            for r in job.results:
                resolution = job.resolutions.get(r.position)
                label = "(unavailable track)" if r.track is None else f"{', '.join(r.track.artists)} - {r.track.title}"
                items.append({"position": r.position, "status": r.status, "label": label, "reason": r.reason,
                              "resolution": resolution})
                if r.track is not None and (r.status == "failed" or resolution):
                    review.append(self._card(r, resolution))
            return {
                "id": job.id, "status": job.status, "name": job.name, "total": job.total,
                "processed": len(job.results), "error": job.error, "items": items, "review": review,
                "pending": sum(1 for r in job.results if self._is_pending(job, r)),
                "summary": summary(job.results) if job.results else "",
                "can_archive": bool(job.out_dir and job.out_dir.is_dir() and any(job.out_dir.glob("*.mp3"))),
            }

    @staticmethod
    def _card(r: TrackResult, resolution: str | None) -> dict:
        t = r.track
        return {
            "position": r.position,
            "resolution": resolution,
            "reason": r.reason,
            "track": {"title": t.title, "artists": t.artists, "album": t.album, "year": t.year,
                      "duration_s": round(t.duration_ms / 1000), "cover_url": t.cover_url},
            "candidates": [{"url": c.url, "video_id": youtube_id(c.url), "source": c.source, "title": c.title,
                            "channel": c.channel, "duration_s": c.duration_s, "score": round(c.score, 1)}
                           for c in r.candidates],
        }
