# TikDownload API

FastAPI backend with GetInSaver-based TikTok URL retrieval, PostgreSQL metadata, S3-compatible object storage, Redis/RQ video-processing queue, and FFmpeg conversion/compression.

## Quick start (Docker)

1. Copy `.env.example` to `.env` in this folder.
2. Set `GETINSAVER_API_KEY` to your GetInSaver API key. GetInSaver is an independent provider; its API usage may consume credits. Confirm provider terms, supported content, and rights before using it.
3. Change the default PostgreSQL and MinIO passwords in `.env` before using anything beyond local development.
4. Start services:

```bash
docker compose up --build -d
```

Services:
- **API:** http://localhost:8000
- **PostgreSQL:** internal port 5432; durable jobs/media metadata
- **Redis:** queue backing
- **RQ worker:** FFmpeg jobs
- **MinIO:** local S3-compatible storage at http://localhost:9000; console at http://localhost:9001
- **MinIO initializer:** creates the `tikdownload-media` bucket

The stack uses named volumes for PostgreSQL, Redis, and MinIO. API and worker share object storage, not container-local media files. MinIO is for local development; for production, use managed object storage such as Cloudflare R2 or AWS S3 and supply the S3-compatible credentials/endpoint.

## TikTok URL retrieval

The URL download endpoint uses GetInSaver's resolver:

```http
POST https://developers.getinsaver.com/v1/resolve
Authorization: Bearer <GETINSAVER_API_KEY>
Content-Type: application/json

{"service":"tiktok","url":"<validated TikTok URL>","max_results":1}
```

TikDownload selects the first `video` item, downloads it from the provider's HTTPS media URL, and stores it in object storage. Photo/carousel items are not presented as video downloads. The provider is independent and not an official TikTok API. Its credits, service terms, availability, and supported links are controlled by the provider.

Configure the key using `GETINSAVER_API_KEY`. The API endpoint returns a configuration error until this key is set. The backend validates HTTPS and public DNS for the returned media URL, refuses redirects, checks the content type, and enforces `MAX_UPLOAD_MB`.

Provider docs: https://developers.getinsaver.com/tiktok-downloader-api

## PostgreSQL and object storage

`backend/app/persistence.py` uses PostgreSQL when `DATABASE_URL` is set; SQLite remains the local test/fallback database. PostgreSQL stores media metadata and processing-job status.

`backend/app/storage.py` uses local filesystem storage when S3 settings are absent, or S3-compatible storage when all settings are configured:
- `S3_BUCKET`
- `S3_ENDPOINT_URL`
- `S3_REGION`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`

This adapter works with MinIO locally and can be configured for Cloudflare R2 or AWS S3. Media objects are stored under `media/` keys. Download responses temporarily localize an object before serving it, and workers localize source files before FFmpeg processing and upload completed output back to storage.

### Cloudflare R2 configuration

Create an R2 bucket and an API token scoped to Object Read & Write for that bucket. Set these in `.env` (and set `DATABASE_URL` if using a managed PostgreSQL service):

```env
S3_BUCKET=your-bucket
S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
S3_REGION=auto
S3_ACCESS_KEY_ID=<R2_ACCESS_KEY_ID>
S3_SECRET_ACCESS_KEY=<R2_SECRET_ACCESS_KEY>
DATABASE_URL=<managed-postgresql-connection-string>
```

The local Compose API and worker use these same variables; MinIO is started for local development. For production with managed PostgreSQL and Cloudflare R2, use the separate `docker-compose.cloud.yml` stack instead. It does not start local PostgreSQL or MinIO and requires the cloud connection/credentials in `.env`:

```bash
docker compose -f docker-compose.cloud.yml up --build -d
```

R2 uses an S3-compatible API; refer to Cloudflare's setup guide for creating buckets, credentials, and endpoint URLs.

**Important:** existing SQLite records/media are not automatically migrated to PostgreSQL/object storage. Back up and migrate any data you need before switching production settings.

## API endpoints

- `GET /health` — API, database, and queue status
- `POST /api/v1/validate` — validate TikTok HTTPS URL format
- `POST /api/v1/download` — retrieve a video using GetInSaver and store it temporarily
- `POST /api/v1/media/upload` — upload an authorized MP4, WebM, or MOV
- `POST /api/v1/media/{id}/process?operation=convert|compress&resolution=keep|1080|720|480` — queue FFmpeg processing
- `GET /api/v1/jobs/{job_id}` — status, progress, and output metadata
- `GET /api/v1/media/{id}/download` — temporary download for retrieved/uploaded/processed media

## Video processing

- Conversion: H.264/AAC MP4, CRF 23
- Compression: H.264/AAC MP4, CRF 28
- Resolution: keep, 1080p, 720p, or 480p while preserving aspect ratio
- RQ progress is persisted in PostgreSQL
- Temporary links default to one hour (`MEDIA_TTL_SECONDS`)

Example upload:

```bash
curl -X POST http://localhost:8000/api/v1/media/upload -F "file=@my-video.mp4"
```

Queue compression:

```bash
curl -X POST "http://localhost:8000/api/v1/media/MEDIA_ID/process?operation=compress&resolution=720"
```

## Production configuration

For production, use managed PostgreSQL and managed object storage; set strong secrets; configure TLS/reverse proxy and correct frontend `CORS_ORIGINS`; use a shared rate limiter; monitor provider credits, request errors, storage costs, and worker capacity; and configure a scheduled cleanup task for expired objects. The current rate limiter is process-local and expiry cleanup is triggered by API activity, so production scaling still requires follow-up hardening.

## Local tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

FFmpeg is mocked in the unit tests. Test the Docker stack and real FFmpeg processing before public production launch.
