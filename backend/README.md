# TikDownload API

FastAPI backend for TikDownload. It supports temporary video storage, FFmpeg conversion/compression, persistent job/media metadata, and provider-based TikTok URL retrieval.

## Endpoints

- `GET /health` — health/version
- `POST /api/v1/validate` — validate HTTPS TikTok URL format
- `POST /api/v1/download` — retrieve through the configured authorized provider; returns 501 until configured
- `POST /api/v1/media/upload` — upload authorized MP4, WebM, or MOV files
- `POST /api/v1/media/{id}/process?operation=convert|compress&resolution=keep|1080|720|480` — queue conversion/compression
- `GET /api/v1/jobs/{job_id}` — status, progress, and output metadata
- `GET /api/v1/media/{id}/download` — download retrieved, uploaded, or processed media

## Docker Compose deployment

From this directory:

```bash
docker compose up --build -d
```

Services:
- **API:** `http://localhost:8000`
- **Redis:** persistent queue backing
- **RQ worker:** FFmpeg processing service

The named `tikdownload-data` volume stores uploaded/processed media and the SQLite metadata database. Redis uses append-only persistence. Both the API and worker share the media/database volume.

Before public deployment, set a production frontend origin for `CORS_ORIGINS`, secure secrets, TLS/reverse proxy, and suitable upload limits.

## Run locally without Redis

Python 3.10+ recommended. Install FFmpeg separately and ensure it is on PATH.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Without `REDIS_URL`, processing uses a local development thread. With Redis configured, jobs are enqueued to RQ and the separate worker processes them.

API docs: `http://127.0.0.1:8000/docs`

## Video processing

Conversion uses H.264/AAC MP4; compression uses CRF 28 (conversion uses CRF 23). Resolution presets preserve aspect ratio and allow keep, 1080p, 720p, or 480p. Progress is persisted while FFmpeg runs. Temporary output links expire after one hour by default.

Example upload:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/media/upload -F "file=@my-video.mp4"
```

Queue a compression job (replace `MEDIA_ID`):

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/media/MEDIA_ID/process?operation=compress&resolution=720"
```

Poll status using the returned `job_id`:

```bash
curl http://127.0.0.1:8000/api/v1/jobs/JOB_ID
```

When completed, the job response includes a `download_url`, `size_bytes`, `original_size_bytes`, and `size_change_bytes`.

## TikTok URL retrieval provider

TikDownload has a provider adapter, but no retrieval provider is bundled or configured by default. Set:

- `TIKTOK_RETRIEVAL_API_URL` — provider API endpoint
- `TIKTOK_RETRIEVAL_API_TOKEN` — bearer token

TikDownload POSTs JSON `{"url":"<validated TikTok URL>"}` to the provider endpoint. Provider response format:

```json
{
  "download_url": "https://public-provider-cdn.example/video.mp4",
  "filename": "video.mp4"
}
```

The media URL must be HTTPS, resolve to public IP addresses, and return a video content type. Redirects are not followed, and retrieval size is limited by `MAX_UPLOAD_MB`. The provider endpoint must be chosen/configured by the operator and must be used only for content the requester is authorized to retrieve. This adapter does not scrape TikTok or bypass access controls.

## Environment configuration

- `CORS_ORIGINS` — allowed browser origins
- `RATE_WINDOW_SECONDS` — limiter window (default 60)
- `RATE_LIMIT_REQUESTS` — requests per client/window (default 30)
- `MAX_UPLOAD_MB` — upload/retrieval size limit (default 80)
- `MEDIA_TTL_SECONDS` — temporary link expiry (default 3600)
- `MEDIA_DIR` — media file storage directory
- `TIKDOWNLOAD_DB_PATH` — SQLite metadata file
- `REDIS_URL` — enable Redis/RQ queue (unset for local thread fallback)
- `TIKTOK_RETRIEVAL_API_URL` and `TIKTOK_RETRIEVAL_API_TOKEN` — provider adapter settings

## Production limitations

SQLite and local shared volume are suitable for a single-host deployment. Multi-host API/worker scaling should move metadata to PostgreSQL and media to object storage. Rate limiting remains process-local. Expiry cleanup is request-triggered and should be scheduled in production. FFmpeg is mocked in the unit test; validate actual FFmpeg behavior in Docker before opening the service publicly.
