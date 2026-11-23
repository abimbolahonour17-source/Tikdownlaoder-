# TikDownload

A responsive frontend plus FastAPI backend for video retrieval (through a configured authorized provider), uploads, FFmpeg conversion/compression, queued jobs, and temporary downloads.

## Frontend

- `index.html`: page markup
- `styles.css`: responsive dark-purple styling
- `script.js`: clipboard paste, URL validation, temporary video upload/download, background job polling, progress UI, mobile navigation

Open `index.html` directly to view the interface. For API-backed validation, run the backend and serve the frontend through a local web server (for example, `python3 -m http.server 5500`).

## Backend

The API supports provider-based TikTok URL retrieval, temporary uploads, FFmpeg conversion/compression, background jobs, live progress, and file-size comparison. Retrieval is not turnkey: configure an authorized provider adapter as documented. See `backend/README.md` for details.

FastAPI backend lives in `backend/`.

### Endpoints

- `GET /health` — health and version check
- `POST /api/v1/validate` — validate an HTTPS TikTok link
- `POST /api/v1/download` — retrieves video via configured authorized provider; otherwise 501
- `POST /api/v1/media/upload` — uploads authorized MP4/WebM/MOV files
- `POST /api/v1/media/{id}/process` — queues FFmpeg conversion/compression (Redis/RQ in Compose; thread fallback locally)
- `GET /api/v1/jobs/{job_id}` — persistent job status/progress
- `GET /api/v1/media/{id}/download` — serves retrieved, original, or processed temporary media

Interactive API docs are available at `/docs` when the API is running.

### Docker deployment (API + Redis + worker)

From the backend folder:

```bash
cd backend
docker compose up --build -d
```

The API runs on `http://localhost:8000`. Redis and the RQ worker run separately. The named `tikdownload-data` volume stores the media files and SQLite metadata; Redis uses append-only persistence for the queue. Configure provider credentials and `CORS_ORIGINS` before deploying to a public server.

### Run API locally

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

### Configure API/frontend

Optional environment variables:

- `CORS_ORIGINS`: comma-separated allowed origins. Defaults to common local frontend ports.
- `RATE_WINDOW_SECONDS`: rate-limit window (default 60 seconds).
- `RATE_LIMIT_REQUESTS`: requests per client per window (default 30).
- `MAX_UPLOAD_MB`: maximum uploaded video size (default 80 MB).
- `MEDIA_TTL_SECONDS`: temporary download-link lifetime (default 3600 seconds).
- `TIKDOWNLOAD_DB_PATH`: SQLite metadata path.
- `REDIS_URL`: enables RQ queue; unset uses a process-local thread for development.
- `TIKTOK_RETRIEVAL_API_URL` and `TIKTOK_RETRIEVAL_API_TOKEN`: configured retrieval provider.

Frontend API base is same-origin by default. To use a separate API host, define `window.TIKDOWNLOAD_API_BASE` before loading `script.js` in `index.html`.

### Tests

From the `backend` directory:

```bash
pytest
```

## Backend safety notes

- User-submitted URLs are not fetched by this API.
- Validation uses a hostname allowlist and HTTPS-only policy.
- The basic limiter is in-memory; for production multi-instance deployments, replace it with a shared limiter and review proxy/IP handling.
- Do not add a downloader that bypasses access controls, private-content restrictions, or platform safeguards. Before any retrieval integration, verify its terms, legal basis, and reliability.

## Roadmap

1. Deploy API and configure frontend API origin.
2. Add automated tests/CI and verify deployment.
3. Review download capability and platform constraints before implementing retrieval.
4. Add persistent/shared rate limiting and production observability if needed.
