# Spotify Playlist Downloader — Design

## Goal
CLI tool. Input: private Spotify playlist URL. Output: local mp3 files (accurate matches only), numbered by playlist position, plus a list of tracks that could not be downloaded.

Personal use. Audio is sourced from YouTube Music and YouTube (Spotify API gives metadata only). Users are responsible for rights/terms compliance.

## Non-goals (this increment)
- UI. Next increment: swipe UI to review tracks missing after first search, with audio preview. This increment must store the data that UI needs (see `report.json`).

## Flow
playlist URL -> Spotify metadata -> search YouTube Music + YouTube per track -> score candidates -> download best above threshold -> convert + tag -> report.

## Auth
- Playlist is private: Spotify OAuth Authorization Code with PKCE (`spotipy.SpotifyPKCE`), scope `playlist-read-private playlist-read-collaborative`.
- `.env`: `SPOTIFY_CLIENT_ID`, `SPOTIFY_REDIRECT_URI` (default `http://127.0.0.1:8888/callback`). No client secret needed.
- First run opens browser for login; token cached in `.cache` (gitignored) and refreshed automatically.
- Existing `SPOTIFY_API_KEY` in `.env` is not used; user registers a Spotify app and sets the Client ID.

## Modules (`playlist_download/`)
- `config.py` — load `.env`, validate, check `ffmpeg` on PATH.
- `spotify.py` — fetch playlist (paginated). Per track: position, title, all artists, album, duration_ms, ISRC, release year, explicit, cover URL.
- `matcher.py` — search both sources, score, return ranked candidates.
- `downloader.py` — yt-dlp audio download, ffmpeg -> mp3 320k, mutagen tags + cover art.
- `report.py` — build/write `failed.txt`, `report.json`, console summary.
- `main.py` — CLI: `python main.py <playlist_url> [--out DIR] [--threshold N]`.

## Matching
Queries per track: YouTube Music (songs filter) `artist title`; YouTube `artist title`, `artist title official audio`, `artist title topic`.

Score (0-100), per candidate:
- Duration delta to Spotify (strongest): within 3s full points, decays to 0 at ~15s.
- Fuzzy title similarity (`rapidfuzz`) after normalizing (strip feat./brackets/punctuation).
- Artist match in channel name or title.
- Bonus: "Topic" channel, official artist channel, YT Music album match.
- Penalty: live, cover, remix, karaoke, sped up, slowed, reverb, lyrics, instrumental — unless the Spotify title contains the same word.

Pick highest score >= threshold (default 70). Otherwise track is "unmatched": skipped, never guess.

## Output
- `downloads/<playlist name>/NNN - Artist - Title.mp3`; `NNN` = playlist position, zero-padded to playlist size width. Failed tracks leave gaps.
- Filenames sanitized for Windows.
- Re-run: tracks whose position prefix already has a file are skipped; only missing/failed are retried.
- `failed.txt`: position, artist, title, reason (`no match above threshold` / `download error` / `conversion error`), best rejected candidate + score.
- `report.json`: for every track: status, chosen URL + score, and top 5 candidates (url, source, title, channel, duration, score). The next-increment UI reads this for failed tracks.
- Console: progress per track, end summary `N downloaded / M failed` and the failed list.

## Errors
- Per-track failures are caught, logged, retried up to 2 times for network/download errors, then recorded as failed; run continues.
- Missing ffmpeg or credentials: fail fast at startup with a clear message.

## Testing
- Unit (offline): scoring (duration, penalties, artist/title normalization), filename sanitizing + zero-padding, skip-existing detection, report generation.
- Spotify/YouTube calls behind thin interfaces so matcher is testable with fixtures.
- Manual: run on a small private playlist.

## Dependencies
`spotipy`, `yt-dlp`, `ytmusicapi`, `mutagen`, `rapidfuzz`, `python-dotenv`, `pytest`.
