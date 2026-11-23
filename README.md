# TikDownload

Responsive video utility frontend with a FastAPI backend for provider-based TikTok retrieval, authorized uploads, FFmpeg conversion/compression, queued jobs, PostgreSQL metadata, and S3-compatible media storage.

## Frontend
- `index.html`: interface
- `styles.css`: responsive styles
- `script.js`: URL validation, retrieval, uploads, processing progress, and downloads

Open `index.html` to preview. For API-backed features, serve it locally and start the backend.

## Backend features
- TikTok URL retrieval through the independent GetInSaver API provider (requires provider API key; not an official TikTok API)
- PostgreSQL for job/media metadata (SQLite remains for local tests)
- S3-compatible object storage (MinIO local development, AWS S3/Cloudflare R2-compatible configuration for cloud)
- Redis/RQ background FFmpeg processing
- Authorized video uploads and temporary download links

## Local Docker stack
See `backend/README.md`. From the backend folder, copy `.env.example` to `.env`, add your GetInSaver API key, replace default local passwords, and run:

```bash
docker compose up --build -d
```

The stack starts API, PostgreSQL, Redis, RQ worker, MinIO, and an initialization service that creates the media bucket. The API is at `http://localhost:8000`; MinIO console is at `http://localhost:9001`.

## API
- `GET /health`
- `POST /api/v1/validate`
- `POST /api/v1/download`
- `POST /api/v1/media/upload`
- `POST /api/v1/media/{id}/process`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/media/{id}/download`

## Important
GetInSaver is an independent third-party service; retrieval works only with a configured key, subject to its availability, terms, and credit limits. Retrieve only content you are authorized to download. For Vercel deployment, the TikTok retrieval route can return short-lived direct S3-compatible download links when Supabase Storage S3 credentials are configured; otherwise it falls back to the API download route. The upload and FFmpeg processing UI is hidden outside local development, and those API routes return a clear 503 on Vercel until a durable worker/direct-upload flow is added. Background processing is intentionally not started on Vercel. Production deployment still needs managed secrets, TLS, shared rate limiting, scheduled media expiry, operational monitoring, and real provider/storage validation.
