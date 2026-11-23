# TikDownload API

FastAPI backend starter for TikDownload.

## Current endpoints

- `GET /health` — API health/version
- `POST /api/v1/validate` — validates HTTPS TikTok URL hosts and path
- `POST /api/v1/download` — validates the URL, then returns HTTP 501 with a clear provider-not-configured response. Retrieval is intentionally not enabled.

## Local run

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

Example validate request:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/validate \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.tiktok.com/@creator/video/123456"}'
```

## Configuration

- `CORS_ORIGINS`: comma-separated allowed origins (default includes local dev ports)
- `RATE_WINDOW_SECONDS`: rate limit window, default 60
- `RATE_LIMIT_REQUESTS`: max API requests per client per window, default 30

## Security notes

- The API does not fetch user-submitted URLs, so this initial version avoids SSRF from arbitrary URL fetching.
- Host validation is allowlist-based; only HTTPS TikTok hosts are accepted.
- Rate limit is in-memory and resets when the process restarts. Use a shared limiter (e.g. Redis) for multi-instance production.
- Download processing is not implemented. Before adding it, confirm that the retrieval mechanism is permitted, reliable, and does not bypass access controls. Only support content users have rights or permission to save.
