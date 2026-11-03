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
2. Add this Redirect URI exactly: `http://127.0.0.1:8888/callback`
3. Copy the app's **Client ID**.
4. Copy `.env.example` to `.env` and fill it in:

```
SPOTIFY_CLIENT_ID=your_client_id_here
# optional, default shown
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

Windows: `copy .env.example .env`. Linux: `cp .env.example .env`.

## 4. Run

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
