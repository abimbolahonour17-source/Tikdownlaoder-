# TikDownload

A responsive frontend prototype plus a small FastAPI service for validating TikTok URLs.

> **Download status:** This repository includes URL validation and a download endpoint placeholder. It does not retrieve video files. Use TikTok's built-in save feature or an authorized source. Only save content you own or have permission to download.

## Frontend

- `index.html`: page markup
- `styles.css`: responsive dark-purple styling
- `script.js`: clipboard paste, client-side URL checks, API validation call, mobile navigation

Open `index.html` directly to view the interface. For API-backed validation, run the backend and serve the frontend through a local web server (for example, `python3 -m http.server 5500`).

## Backend

The API supports temporary upload and download of video files users own or are authorized to use. See `backend/README.md` for endpoint details. TikTok URL retrieval itself is not enabled.

FastAPI backend lives in `backend/`.

### Endpoints

- `GET /health` — health and version check
- `POST /api/v1/validate` — validate an HTTPS TikTok link
- `POST /api/v1/download` — returns `501 DOWNLOAD_PROVIDER_NOT_CONFIGURED` for supported URLs because download retrieval is not implemented

Interactive API docs are available at `/docs` when the API is running.

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
