# TikDownload API

FastAPI backend for TikTok link retrieval through GetInSaver, temporary media downloads, PostgreSQL metadata, and Vercel Blob object storage.

## Local development

1. Copy `.env.example` to `.env` and configure `GETINSAVER_API_KEY`.
2. For local Docker development, use the included PostgreSQL/Redis/MinIO stack only if you are testing the legacy worker path. The deployed Vercel media path uses Vercel Blob; it does not use MinIO or S3.
3. Install and run tests:

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

## Media storage on Vercel

The Vercel deployment stores retrieved media in Vercel Blob. Configure one of these supported credential options in the Vercel project that owns the Blob store:

- Recommended: Vercel Blob integration/OIDC with both `VERCEL_OIDC_TOKEN` (provided by the Vercel runtime) and `BLOB_STORE_ID` (the store identifier).
- Or a server-side `BLOB_READ_WRITE_TOKEN` / `VERCEL_BLOB_READ_WRITE_TOKEN` token.

Set `BLOB_ACCESS` to match the actual Blob store's access mode (`public` or `private`). Do not expose a read/write token in frontend code or commit it to GitHub. The API keeps the Blob URL private and streams downloads through an ID-based endpoint.

## Required production configuration

- `GETINSAVER_API_KEY`: API key for the independent GetInSaver provider.
- `BLOB_READ_WRITE_TOKEN` (or Vercel OIDC plus `BLOB_STORE_ID`): server-side Blob access.
- `BLOB_ACCESS`: must match the Blob store configuration.
- `DATABASE_URL`: managed PostgreSQL connection string. Without it, the fallback SQLite database is under `/tmp` and is ephemeral on Vercel; production media metadata and expiry records will not survive instance replacement.
- `CORS_ORIGINS`: comma-separated exact frontend origins.
- `MEDIA_TTL_SECONDS`: temporary media lifetime (default 3600).

## API endpoints

- `GET /health`
- `POST /api/v1/validate`
- `POST /api/v1/download`
- `POST /api/v1/media/upload` (returns 503 on Vercel; local development only)
- `POST /api/v1/media/{id}/process` (returns 503 on Vercel; local development only)
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/media/{id}/download`

## Operational limitations

Vercel's API route retrieves the provider's media into a temporary file, uploads it to Blob, then removes the temporary file. Download links are mediated by the API and expire according to metadata. Cleanup currently runs when API requests occur; configure a scheduled cleanup invocation before relying on strict deletion deadlines. Configure managed PostgreSQL before production use. Shared rate limiting, worker-based FFmpeg processing, upload streaming, real provider tests, and storage integration tests remain separate production-hardening tasks.

Retrieve only content you have permission to download. GetInSaver is an independent third-party provider, not an official TikTok API; its availability, credits, and terms apply.
