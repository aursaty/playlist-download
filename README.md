# Playlist Downloader

Reads a Spotify playlist (private playlists supported) and downloads each track as a tagged mp3.
Spotify only supplies metadata. Audio is found on YouTube Music and YouTube, and each candidate is
scored on duration, title, artist and version (live/remix/cover) so the download is the right song.
Tracks without a confident match are skipped and listed instead of guessed.

For personal use. You are responsible for complying with the terms of the services involved and with
copyright law in your country.

## Requirements

- Python 3.11+
- ffmpeg (includes `ffprobe`) on your PATH
- A Spotify account and a free Spotify developer app (Client ID only, no secret)

## 1. Install ffmpeg

**Windows** (PowerShell):

```powershell
winget install Gyan.FFmpeg
```

Close and reopen the terminal, then check: `ffmpeg -version`.

**Linux**:

```bash
sudo apt install ffmpeg        # Debian/Ubuntu
sudo dnf install ffmpeg        # Fedora (needs RPM Fusion)
sudo pacman -S ffmpeg          # Arch
```

## 2. Install the project

**Windows** (PowerShell, in the project folder):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activate script, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or skip activation and call
`.venv\Scripts\python` directly (see step 4).

**Linux / macOS**:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Create the Spotify app

1. Open https://developer.spotify.com/dashboard and create an app.
2. Add these Redirect URIs exactly (one is for the web app, one for the command line):
   - `http://127.0.0.1:8000/callback` (web app)
   - `http://127.0.0.1:8888/callback` (command line)
3. Copy the app's **Client ID**.
4. Copy `.env.example` to `.env` and fill it in:

```
SPOTIFY_CLIENT_ID=your_client_id_here
# optional, default shown
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

Windows: `copy .env.example .env`. Linux: `cp .env.example .env`.

## Web app (vibedl)

A local page: paste a playlist link, watch the songs download, then swipe through the songs that could
not be matched on their own, listen to the candidates and pick the right one. At the end you can download a
zip with the finished playlist.

```bash
python app.py                  # Windows without activating the venv: .venv\Scripts\python app.py
```

Open http://127.0.0.1:8000 and press **connect spotify** once (the login happens in the page, token is
stored in `.cache-web`). Then:

1. Paste the playlist link and press **get the songs**.
2. Songs that match confidently download by themselves. The rest appear as cards.
3. On a card, press **listen** to hear the candidate. Then:

| Action | Mouse / touch | Keyboard |
|---|---|---|
| take this candidate | drag right, or **this one** | right arrow |
| show the next candidate | drag left, or **next match** | left arrow |
| previous candidate | **back** | up arrow |
| skip the song | drag down, or **skip song** | down arrow |
| listen | **listen** | space |

   Know the right video? Paste its YouTube link under the card and press **use this link**.
4. When every card is sorted, press **download zip**. The zip holds the numbered mp3s in playlist order.
   Skipped songs leave a gap in the numbering. The zip button is also available while you are still
   reviewing, with what is finished so far.

Files are written to `downloads/<playlist name>/` as with the command line, and re-running a playlist only
fetches what is missing. One playlist is processed at a time.

Options: `--host`, `--port` (default 8000), `--out` (download folder), `--cache` (login token file). The same
can be set with `HOST`, `PORT`, `DOWNLOAD_DIR`, `SPOTIFY_CACHE_PATH`. If you change the port, also set
`WEB_REDIRECT_URI` in `.env` and register that URI in the Spotify dashboard.

## Docker

Needs Docker with Compose. ffmpeg is included in the image, so you do not install it on the host.

```bash
cp .env.example .env           # Windows: copy .env.example .env   then set SPOTIFY_CLIENT_ID
docker compose up --build
```

Open http://127.0.0.1:8000, connect Spotify once, and use it as described above. Finished files appear in
`./downloads` on the host. The Spotify login token lives in the `vibedl-auth` volume, so it survives restarts.

- The port is published on `127.0.0.1` only, so only this machine can reach the app. Do not expose it to a
  network: it has no password.
- To reach it under another host name, set `WEB_ALLOWED_HOSTS=name` in `.env`. Spotify only accepts
  `http://127.0.0.1` or `https` redirect addresses, so set `WEB_REDIRECT_URI` to a matching one and register it.
- On Linux, if `./downloads` is created by root, run `mkdir downloads` first, or start with
  `UID=$(id -u) GID=$(id -g) docker compose up --build` after adding `user: "${UID}:${GID}"` to the service.
- Update the downloader when YouTube changes something: `docker compose build --no-cache`.

## 4. Run from the command line

**Windows** (PowerShell):

```powershell
python main.py "https://open.spotify.com/playlist/<id>"
# without activating the venv:
.venv\Scripts\python main.py "https://open.spotify.com/playlist/<id>"
```

**Linux / macOS**:

```bash
python main.py "https://open.spotify.com/playlist/<id>"
```

Quote the URL: `?` and `&` break unquoted shell commands. A bare playlist id or a
`spotify:playlist:<id>` URI also works.

On the first run a browser window opens for the Spotify login (needed for private playlists). The
token is cached in `.cache` and refreshed automatically.

Options:

| Option | Default | Meaning |
|---|---|---|
| `--out DIR` | `downloads` | Base output folder |
| `--threshold N` | `70` | Minimum match score (0-100). Higher = stricter |

## Output

```
downloads/<playlist name>/
  001 - Artist - Title.mp3     numbered by playlist position
  003 - Artist - Title.mp3     a gap (002 missing) means track 2 was not downloaded
  failed.txt                   tracks not downloaded: position, artist, title, reason, best rejected match
  report.json                  every track: status, chosen URL, top 5 candidates with scores
```

At the end of a run the same failed list is printed with a `N downloaded / M failed` summary.

Re-running the same command skips files that already exist and retries only the missing ones.
Reordering the playlist between runs can leave an old file next to a new one at the same number.

## Troubleshooting

- **`ffmpeg not found on PATH`**: install ffmpeg and reopen the terminal.
- **`SPOTIFY_CLIENT_ID missing`**: create `.env` as in step 3, in the folder you run from.
- **`INVALID_CLIENT: Invalid redirect URI`**: the Redirect URI in the Spotify dashboard must match
  `SPOTIFY_REDIRECT_URI` exactly.
- **`Spotify error` / `Unexpected Spotify response`**: Spotify restricts what new apps can read. Make sure
  you are logged in as the playlist owner or a collaborator.
- **Many `download error` lines**: YouTube changed something. Update the downloader:
  `pip install -U yt-dlp`.
- **Wrong or missing songs**: look at `failed.txt` for the best rejected candidate. Lower `--threshold`
  to accept weaker matches (not below 69, see the note below).

## Development

```bash
pip install -r requirements.txt
python -m pytest -q
```

Note: a candidate whose artist does not appear in the video title or channel is capped at score 69,
so a threshold below 69 can let wrong-artist matches through.
