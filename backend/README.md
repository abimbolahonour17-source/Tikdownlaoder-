# TikDownload API

FastAPI backend for TikDownload.

## Endpoints

- `GET /health` — health/version
- `POST /api/v1/validate` — validate HTTPS TikTok URL format
- `POST /api/v1/download` — returns 501; TikTok URL-to-file retrieval is not available
- `POST /api/v1/media/upload` — upload authorized MP4, WebM, or MOV files
- `POST /api/v1/media/{id}/process?operation=convert|compress&resolution=keep|1080|720|480` — convert to MP4 or compress with FFmpeg
- `GET /api/v1/media/{id}/download` — download uploaded or processed temporary media

Conversion uses H.264 video and AAC audio in an MP4 container. Compression uses CRF 28; conversion uses CRF 23. Resolution can be kept or scaled down to 1080p, 720p, or 480p. Processing runs in a background thread and reports progress from FFmpeg's progress output when source duration is available. Jobs return `queued`, `running`, `completed`, or `failed` status. A hard timeout during the live-output read still needs to be added and tested. Temporary files expire after one hour by default.

## Run locally

Python 3.10+ recommended. Install FFmpeg separately and make sure `ffmpeg` is on PATH.

```bash
cd backend
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

The Dockerfile installs FFmpeg for container deployments.

## Upload and process example

```bash
curl -X POST http://127.0.0.1:8000/api/v1/media/upload -F "file=@my-video.mp4"
```

Upload response contains a media `id`. Use that ID to process:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/media/MEDIA_ID/process?operation=compress&resolution=720"
```

The processing response includes a temporary download URL. Convert example: `operation=convert&resolution=keep`.

## Configuration

- `CORS_ORIGINS`: allowed frontend origins
- `RATE_WINDOW_SECONDS`: rate limit window (default 60)
- `RATE_LIMIT_REQUESTS`: requests per client/window (default 30)
- `MAX_UPLOAD_MB`: upload limit (default 80)
- `MEDIA_TTL_SECONDS`: download expiry (default 3600)
- `MEDIA_DIR`: storage folder (default /tmp/tikdownload-media)

## TikTok URL retrieval status

This backend intentionally does not scrape or fetch video bytes from TikTok URLs. TikTok's official developer APIs offer public-video metadata/display and creator upload/posting flows, but do not provide a general-purpose endpoint for downloading arbitrary TikTok video URLs. A retrieval feature would require a lawful, authorized source/API that provides media files and must not bypass privacy or access controls. The current URL field only validates a TikTok link.

## Deployment limitations

- Upload and FFmpeg processing are synchronous request operations; large videos may need a background queue.
- Media records and rate limiting are in-memory, and the default container filesystem may be ephemeral. Production should use shared object storage, persistent job records, and a queue.
- Expiry cleanup is request-triggered rather than a scheduler.
- Tests run in GitHub Actions; FFmpeg itself is mocked in the processing test.
