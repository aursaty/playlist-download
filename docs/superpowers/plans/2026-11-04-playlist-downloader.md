# Spotify Playlist Downloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI that reads a private Spotify playlist, finds each track on YouTube Music/YouTube with scored matching, downloads tagged mp3s numbered by playlist position, and reports tracks that failed.

**Architecture:** Spotify gives metadata only (spotipy, OAuth PKCE). `matcher` queries ytmusicapi and yt-dlp search, `scoring` ranks candidates, `downloader` fetches audio with yt-dlp and tags with mutagen, `report` writes `failed.txt` / `report.json`. Network access sits behind thin functions so scoring, naming and reporting are tested offline.

**Tech Stack:** Python 3.11+, spotipy, yt-dlp, ytmusicapi, mutagen, rapidfuzz, python-dotenv, pytest. ffmpeg on PATH.

**Spec:** `docs/superpowers/specs/2026-11-04-playlist-downloader-design.md`

## Global Constraints

- Dependencies pinned exactly in `requirements.txt`: `spotipy==2.26.0`, `yt-dlp==2026.10.26`, `ytmusicapi==1.12.3`, `mutagen==1.48.1`, `rapidfuzz==3.14.6`, `python-dotenv==1.2.4`, `pytest==9.2.0`.
- Spotify auth: `spotipy.SpotifyPKCE`, scope `playlist-read-private playlist-read-collaborative`; `.env` keys `SPOTIFY_CLIENT_ID`, `SPOTIFY_REDIRECT_URI` (default `http://127.0.0.1:8888/callback`); token cache `.cache`.
- Output: `downloads/<playlist name>/NNN - Artist - Title.mp3`, `NNN` = playlist position zero-padded to playlist size width; failed tracks leave gaps; mp3 320k.
- Match threshold default 70 (0-100 scale). Below threshold: skip, never guess.
- Candidate duration tolerance: full points within 3s, zero at 15s.
- Download/network errors retried up to 2 times, then recorded as failed; run continues.
- Sources: YouTube Music (songs filter) and YouTube (`artist title`, `artist title official audio`, `artist title topic`).
- Penalty words (unless in Spotify title): live, cover, remix, karaoke, sped up, slowed, reverb, lyrics, instrumental.
- `report.json` stores top 5 candidates per track (url, source, title, channel, duration, score) for the next-increment UI.
- Fail fast at startup if ffmpeg or `SPOTIFY_CLIENT_ID` is missing.

## Review Focus

- Playlist items with no track (deleted/local files/podcast episodes): skipped and listed as failed, no crash. (Task 4)
- Windows-illegal filename chars (`<>:"/\|?*`), trailing dots/spaces, very long names, emoji. (Task 2)
- Same song twice in a playlist: two positions, two files, no collision. (Task 2)
- Candidates with missing/zero duration (YT Music sometimes omits it): scored without crashing, can't win on duration alone. (Task 3)
- Non-Latin titles (Cyrillic, Japanese): normalization must not reduce the title to an empty string. (Task 3)
- Playlist over 100 tracks: pagination returns all, in order. (Task 4)

---

### Task 1: Scaffold and config

**Files:**
- Create: `requirements.txt`, `.gitignore` (`.env`, `.cache`, `downloads/`, `__pycache__/`, `.venv/`), `pytest.ini` (`pythonpath = .`), `playlist_download/__init__.py`, `playlist_download/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `@dataclass Config(client_id: str, redirect_uri: str)`; `load_config() -> Config` (reads `.env`, raises `ConfigError` if `SPOTIFY_CLIENT_ID` missing); `check_ffmpeg() -> None` (raises `ConfigError` if not on PATH, via `shutil.which`); `class ConfigError(Exception)`.

- [ ] **Step 1:** Run `git init`; create venv; write files above; `pip install -r requirements.txt`.
- [ ] **Step 2: Write failing tests** in `tests/test_config.py` (use `monkeypatch`, `load_dotenv` patched out): `test_load_config_defaults_redirect_uri` (only client id set → redirect `http://127.0.0.1:8888/callback`), `test_load_config_missing_client_id_raises`, `test_check_ffmpeg_missing_raises` (patch `shutil.which` → None).
- [ ] **Step 3:** Run `pytest tests/test_config.py -v`. Expected: FAIL (module missing).
- [ ] **Step 4:** Implement `config.py` per Interfaces.
- [ ] **Step 5:** Run `pytest tests/test_config.py -v`. Expected: 3 PASS.
- [ ] **Step 6:** `git add -A && git commit -m "chore: scaffold project and config"` (do not add `.env`).

### Task 2: Models and naming

**Files:**
- Create: `playlist_download/models.py`, `playlist_download/naming.py`, `tests/test_naming.py`

**Interfaces:**
- Produces (`models.py`): `@dataclass Track(position: int, title: str, artists: list[str], album: str, duration_ms: int, isrc: str | None, year: int | None, explicit: bool, cover_url: str | None)`; `@dataclass Candidate(url: str, source: str, title: str, channel: str, duration_s: int | None, album: str | None, score: float = 0.0)` where `source` is `"ytmusic"` or `"youtube"`.
- Produces (`naming.py`): `sanitize(name: str) -> str`; `track_filename(track: Track, width: int) -> str` → `"NNN - Artist1, Artist2 - Title.mp3"` (sanitized, each part capped so the whole stem ≤ 150 chars); `find_existing(out_dir: Path, position: int, width: int) -> Path | None` (matches by `NNN - ` prefix, `.mp3`).

- [ ] **Step 1: Write failing tests:** `test_sanitize_removes_illegal_chars` (`'a<b>:c"/d\\e|f?g*'` has none of `<>:"/\|?*` after), `test_sanitize_strips_trailing_dots_and_spaces` (`"x. . "` → `"x"`), `test_track_filename_pads_to_width` (position 7, width 3 → starts `"007 - "`, ends `".mp3"`), `test_track_filename_long_title_capped` (300-char title → stem ≤ 150), `test_track_filename_keeps_emoji_and_cyrillic`, `test_duplicate_songs_get_distinct_names` (same title at positions 1 and 2 → different names), `test_find_existing_by_prefix` (tmp_path with `003 - A - B.mp3` → found for position 3, `None` for 4).
- [ ] **Step 2:** Run `pytest tests/test_naming.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement both files per Interfaces. `sanitize` replaces illegal chars with `_` and strips trailing `.`/space; also guard Windows reserved names (`CON`, `NUL`, …) by appending `_`.
- [ ] **Step 4:** Run tests. Expected: all PASS.
- [ ] **Step 5:** Commit `feat: models and filename helpers`.

### Task 3: Scoring

**Files:**
- Create: `playlist_download/scoring.py`, `tests/test_scoring.py`

**Interfaces:**
- Consumes: `Track`, `Candidate` from `models.py`.
- Produces: `normalize(text: str) -> str` (casefold, strip `feat.`/`ft.`/bracketed parts/punctuation, collapse spaces; if result is empty return the casefolded stripped original); `score_candidate(track: Track, cand: Candidate) -> float` in 0-100.

Weights (decisions the tests pin): duration up to 40 (linear: 40 at ≤3s delta, 0 at ≥15s; `duration_s` None or 0 → 0 points); title similarity up to 30 (`rapidfuzz.fuzz.token_set_ratio` of normalized titles / 100 × 30); artist up to 20 (any Spotify artist, normalized, found in candidate channel or title; first-artist full 20, other artist 10); bonus up to 10 (channel ends with " - Topic" or equals an artist: +6; `source == "ytmusic"` and normalized album equals normalized `track.album`: +4); penalty −25 per penalty word present in candidate title but not in Spotify title. Clamp to [0, 100].

- [ ] **Step 1: Write failing tests:** `test_exact_topic_match_scores_high` (same duration, same title, channel `"Artist - Topic"` → ≥ 90), `test_duration_off_by_20s_gets_no_duration_points`, `test_live_version_penalized` (title + " (Live)" scores ≥ 25 lower than studio), `test_live_not_penalized_when_in_spotify_title`, `test_missing_duration_does_not_crash_and_cannot_pass_threshold_alone` (`duration_s=None`, unrelated title → < 70), `test_cyrillic_title_normalizes_non_empty` (`normalize("Привет")` ≠ `""`), `test_feat_and_brackets_stripped` (`normalize("Song (feat. X)")` == `normalize("Song")`), `test_wrong_artist_scores_below_threshold`.
- [ ] **Step 2:** Run `pytest tests/test_scoring.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement per weights above.
- [ ] **Step 4:** Run tests. Expected: all PASS.
- [ ] **Step 5:** Commit `feat: candidate scoring`.

### Task 4: Spotify playlist fetch

**Files:**
- Create: `playlist_download/spotify.py`, `tests/test_spotify.py`

**Interfaces:**
- Consumes: `Config`, `Track`.
- Produces: `parse_playlist_id(url_or_id: str) -> str` (accepts `https://open.spotify.com/playlist/<id>?si=…`, `spotify:playlist:<id>`, bare id; raises `ValueError` otherwise); `fetch_playlist(client, playlist_id: str) -> tuple[str, list[Track | None]]` where `client` is any object with `playlist(id, fields=…)` and `next(page)` like `spotipy.Spotify`; returns name and a list indexed by position−1, with `None` for items without a usable track (deleted, local, episode); `make_client(config: Config) -> spotipy.Spotify` using `SpotifyPKCE`.

- [ ] **Step 1: Write failing tests** with a fake client and fixture dicts: `test_parse_playlist_id_url_uri_and_bare`, `test_parse_playlist_id_invalid_raises`, `test_fetch_maps_fields` (title, all artists, album, duration_ms, isrc from `external_ids`, year from `release_date`, cover first image), `test_fetch_skips_none_local_and_episode_items_but_keeps_positions` (middle item `track: None` → `None` at index 1, later tracks keep positions 3, 4…), `test_fetch_paginates_over_100` (fake pages of 100 + 50 → 150 entries in order).
- [ ] **Step 2:** Run `pytest tests/test_spotify.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. Follow `next` until `None`; item is unusable if `track` is None, `is_local` true, or `type != "track"`.
- [ ] **Step 4:** Run tests. Expected: all PASS.
- [ ] **Step 5:** Commit `feat: spotify playlist fetch`.

### Task 5: Matcher

**Files:**
- Create: `playlist_download/matcher.py`, `tests/test_matcher.py`

**Interfaces:**
- Consumes: `Track`, `Candidate`, `score_candidate`.
- Produces: `search_ytmusic(query: str) -> list[Candidate]` (ytmusicapi `search(query, filter="songs")`; map `videoId`→`https://music.youtube.com/watch?v=…`, `duration_seconds`, album name); `search_youtube(query: str) -> list[Candidate]` (yt-dlp `ytsearch5:` with `extract_flat`, `duration` may be None); `rank_candidates(track: Track, searchers: list[Callable[[str], list[Candidate]]] | None = None) -> list[Candidate]` — runs the queries from Global Constraints, de-duplicates by video id, scores each, returns sorted descending, a failing searcher is logged and skipped; `pick_best(ranked: list[Candidate], threshold: float = 70) -> Candidate | None`.

- [ ] **Step 1: Write failing tests** with injected fake searchers (no network): `test_rank_sorts_by_score_desc`, `test_rank_dedups_same_video_across_sources`, `test_rank_survives_searcher_exception`, `test_pick_best_below_threshold_returns_none`, `test_pick_best_returns_top_when_above_threshold`.
- [ ] **Step 2:** Run `pytest tests/test_matcher.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. Network searchers are not unit-tested; they are verified in Task 8's manual run.
- [ ] **Step 4:** Run tests. Expected: all PASS.
- [ ] **Step 5:** Commit `feat: multi-source matcher`.

### Task 6: Downloader and tagging

**Files:**
- Create: `playlist_download/downloader.py`, `tests/test_downloader.py`

**Interfaces:**
- Consumes: `Track`, `Candidate`, `track_filename`.
- Produces: `class DownloadError(Exception)`; `download_audio(url: str, dest: Path) -> None` (yt-dlp `bestaudio`, FFmpegExtractAudio mp3 quality 320, output to `dest` exactly; raises `DownloadError` on failure; retries up to 2 times); `tag_file(path: Path, track: Track, cover_bytes: bytes | None) -> None` (mutagen ID3: TIT2, TPE1 joined, TALB, TDRC year, TRCK position, TSRC isrc, APIC cover when given; creates the tag header if the file has none); `fetch_cover(url: str | None) -> bytes | None` (returns None on any failure).

- [ ] **Step 1: Write failing tests:** `test_tag_file_writes_core_frames` (create minimal valid mp3 bytes fixture in tmp_path, tag, reread with `mutagen.id3.ID3`: title, artists, album, year, ISRC, cover present), `test_tag_file_without_cover`, `test_download_audio_retries_then_raises` (patch yt-dlp call to raise; assert 3 attempts, `DownloadError`), `test_fetch_cover_none_url_returns_none`.
- [ ] **Step 2:** Run `pytest tests/test_downloader.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement per Interfaces; yt-dlp call isolated in one private function so tests can patch it.
- [ ] **Step 4:** Run tests. Expected: all PASS.
- [ ] **Step 5:** Commit `feat: audio download and tagging`.

### Task 7: Report

**Files:**
- Create: `playlist_download/report.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `Track`, `Candidate`.
- Produces: `@dataclass TrackResult(position: int, track: Track | None, status: str, chosen: Candidate | None, candidates: list[Candidate], reason: str | None)` with `status` in `"downloaded"`, `"skipped_existing"`, `"failed"`; `write_reports(out_dir: Path, results: list[TrackResult]) -> None` writes `report.json` (every track; top 5 candidates each; `track` fields `null` for unusable items) and `failed.txt`; `format_failed(results: list[TrackResult]) -> str` and `summary(results) -> str` → `"N downloaded / M failed"` (existing counted as downloaded).

`failed.txt` line format: `NNN | Artist | Title | reason | best rejected: <title> (<score>) <url>`; unusable items: `NNN | (unavailable track) | reason`.

- [ ] **Step 1: Write failing tests:** `test_summary_counts`, `test_failed_text_includes_reason_and_best_rejected`, `test_failed_text_handles_unusable_item`, `test_report_json_has_top5_candidates_only`, `test_no_failures_writes_empty_failed_file`.
- [ ] **Step 2:** Run `pytest tests/test_report.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement per Interfaces.
- [ ] **Step 4:** Run tests. Expected: all PASS.
- [ ] **Step 5:** Commit `feat: failed list and report.json`.

### Task 8: CLI orchestration and manual verification

**Files:**
- Create: `playlist_download/main.py`, `main.py` (root shim calling `playlist_download.main.main()`), `tests/test_main.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `process_track(track: Track | None, position: int, width: int, out_dir: Path, threshold: float, rank=rank_candidates, download=download_audio, tag=tag_file, cover=fetch_cover) -> TrackResult` (injectable collaborators for tests); `main(argv: list[str] | None = None) -> int` with args `playlist` (url/uri/id), `--out DIR` (default `downloads`), `--threshold FLOAT` (default 70); returns 0 even when some tracks failed, 2 on `ConfigError`.

Behavior: width = len(str(playlist length)); existing file for the position → `skipped_existing`; `None` track → failed `unavailable track`; no candidate ≥ threshold → failed `no match above threshold` with candidates kept; `DownloadError` → failed `download error: …`; download into a temp name, rename only after tagging succeeds; print progress per track, then summary and failed list; always call `write_reports`.

- [ ] **Step 1: Write failing tests** with fakes: `test_process_track_downloads_and_names_file`, `test_process_track_skips_existing`, `test_process_track_no_match_records_candidates`, `test_process_track_download_error_recorded_not_raised`, `test_process_track_unavailable_item`, `test_partial_file_not_left_on_failure`.
- [ ] **Step 2:** Run `pytest tests/test_main.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `main.py` per Interfaces. Output folder: `<out>/<sanitized playlist name>/`.
- [ ] **Step 4:** Run `pytest -v`. Expected: full suite PASS.
- [ ] **Step 5 (manual):** Set `SPOTIFY_CLIENT_ID` in `.env`; run `python main.py <small private playlist url>`. Expected: browser login once; mp3s `001 - …` in playlist order with tags and cover; `failed.txt` and `report.json` written; second run skips existing files. Spot-check 3 downloaded files by ear against the Spotify tracks and confirm the network searchers work (adjust `search_ytmusic` / `search_youtube` field mapping if results are empty).
- [ ] **Step 6:** Commit `feat: cli orchestration`.
