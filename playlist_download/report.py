import json
from dataclasses import asdict, dataclass
from pathlib import Path

from playlist_download.models import Candidate, Track

TOP_CANDIDATES = 5


@dataclass
class TrackResult:
    position: int
    track: Track | None
    status: str  # "downloaded" | "skipped_existing" | "failed"
    chosen: Candidate | None
    candidates: list[Candidate]
    reason: str | None


def summary(results: list[TrackResult]) -> str:
    failed = sum(1 for r in results if r.status == "failed")
    return f"{len(results) - failed} downloaded / {failed} failed"


def _failed_line(result: TrackResult, width: int) -> str:
    pos = f"{result.position:0{width}d}"
    if result.track is None:
        return f"{pos} | (unavailable track) | {result.reason}"
    line = f"{pos} | {', '.join(result.track.artists)} | {result.track.title} | {result.reason}"
    if result.candidates:
        best = result.candidates[0]
        line += f" | best rejected: {best.title} ({best.score:.1f}) {best.url}"
    return line


def format_failed(results: list[TrackResult]) -> str:
    width = len(str(len(results)))
    return "\n".join(_failed_line(r, width) for r in results if r.status == "failed")


def write_reports(out_dir: Path, results: list[TrackResult]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    failed_text = format_failed(results)
    (out_dir / "failed.txt").write_text(failed_text + ("\n" if failed_text else ""), encoding="utf-8")
    data = {
        "summary": summary(results),
        "tracks": [
            {
                "position": r.position,
                "status": r.status,
                "reason": r.reason,
                "track": asdict(r.track) if r.track else None,
                "chosen": asdict(r.chosen) if r.chosen else None,
                "candidates": [asdict(c) for c in r.candidates[:TOP_CANDIDATES]],
            }
            for r in results
        ],
    }
    (out_dir / "report.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
