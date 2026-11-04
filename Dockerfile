FROM python:3.13-slim

# ffmpeg (with ffprobe) is required by yt-dlp for the mp3 conversion
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY playlist_download ./playlist_download
COPY main.py app.py ./

ENV HOST=0.0.0.0 \
    PORT=8000 \
    DOWNLOAD_DIR=/data/downloads \
    SPOTIFY_CACHE_PATH=/data/auth/.cache-web \
    PYTHONUNBUFFERED=1

# world-writable so the container also works with `user: "$UID:$GID"` and bind mounts
RUN mkdir -p /data/downloads /data/auth && chmod -R 777 /data
VOLUME ["/data/downloads", "/data/auth"]
EXPOSE 8000

CMD ["python", "app.py"]
