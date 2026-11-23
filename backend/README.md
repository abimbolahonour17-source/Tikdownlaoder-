# TikDownload API

FastAPI backend for TikDownload.

## Endpoints

- `GET /health` — health/version
- `POST /api/v1/validate` — validate an HTTPS TikTok URL
- `POST /api/v1/download` — intentionally returns 501; TikTok retrieval is not integrated
- `POST /api/v1/media/upload` — upload a video you own or have permission to use (MP4, WebM, MOV); stores temporarily and returns a download link
- `GET /api/v1/media/{id}/download` — download the uploaded temporary file

Upload validates the MIME type, extension, file signature, and size. Temporary links default to one hour. Expired media is cleaned when another API request is received.

## Run locally

Python 3.10+ recommended.

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

## Upload example

```bash
curl -X POST http://127.0.0.1:8000/api/v1/media/upload -F "file=@my-video.mp4"
```

The response includes a relative `download_url`, which can be opened using the API origin.

## Configuration

- `CORS_ORIGINS`: allowed frontend origins
- `RATE_WINDOW_SECONDS`: rate limit window (default 60)
- `RATE_LIMIT_REQUESTS`: requests per client/window (default 30)
- `MAX_UPLOAD_MB`: max upload size (default 80)
- `MEDIA_TTL_SECONDS`: temporary link expiration (default 3600)
- `MEDIA_DIR`: storage directory (default /tmp/tikdownload-media)

## Limitations and deployment notes

- This upload/download pipeline stores and serves the user's authorized file; it does not transcode, compress, or download from TikTok.
- TikTok URL retrieval remains disabled. Only use official platform options or a provider integration with appropriate authorization that does not circumvent access controls.
- Temporary records and rate limiting are in-memory. For multi-instance production, use shared storage and a database/queue.
- Expiration cleanup is request-triggered, not a scheduled background task.
- Tests were added but have not yet been run in this environment.
