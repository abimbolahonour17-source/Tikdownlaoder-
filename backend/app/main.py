import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

APP_VERSION = "0.2.0"
ALLOWED_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
RATE_WINDOW_SECONDS = int(os.getenv("RATE_WINDOW_SECONDS", "60"))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "80"))
MEDIA_TTL_SECONDS = int(os.getenv("MEDIA_TTL_SECONDS", "3600"))
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/tmp/tikdownload-media"))
request_times: dict[str, deque[float]] = defaultdict(deque)
media_records: dict[str, dict] = {}

app = FastAPI(title="TikDownload API", description="TikDownload URL validation and authorized video-file upload/download API.", version=APP_VERSION)
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5500").split(",")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

class LinkRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)

class LinkValidation(BaseModel):
    valid: bool
    normalized_url: str | None = None
    message: str

def validate_tiktok_url(value: str) -> str | None:
    try:
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host not in ALLOWED_HOSTS or not parsed.path or parsed.path == "/":
            return None
        return parsed.geturl()
    except (ValueError, TypeError):
        return None

def _cleanup_expired_media():
    now = time.time()
    for media_id, record in list(media_records.items()):
        if record["expires_at"] <= now:
            try:
                Path(record["path"]).unlink(missing_ok=True)
            finally:
                media_records.pop(media_id, None)

@app.middleware("http")
async def basic_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = request_times[key]
        while bucket and now - bucket[0] > RATE_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            return await _rate_limited_response()
        bucket.append(now)
    return await call_next(request)

async def _rate_limited_response():
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again shortly."})

@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}

@app.post("/api/v1/validate", response_model=LinkValidation)
def validate_link(body: LinkRequest):
    normalized = validate_tiktok_url(body.url)
    if not normalized:
        return LinkValidation(valid=False, message="Enter a valid HTTPS TikTok video link.")
    return LinkValidation(valid=True, normalized_url=normalized, message="TikTok URL format looks valid.")

@app.post("/api/v1/download")
def download_video(body: LinkRequest):
    if not validate_tiktok_url(body.url):
        raise HTTPException(status_code=400, detail="Enter a valid HTTPS TikTok video link.")
    raise HTTPException(status_code=501, detail={"code": "DOWNLOAD_PROVIDER_NOT_CONFIGURED", "message": "TikTok URL retrieval is not integrated. Use TikTok's save option where available, or upload a video you own or are authorized to use."})

@app.post("/api/v1/media/upload")
async def upload_authorized_video(file: UploadFile = File(...)):
    """Store a video the user owns or is authorized to use and return a temporary download URL."""
    _cleanup_expired_media()
    accepted_types = {"video/mp4", "video/webm", "video/quicktime"}
    accepted_extensions = {".mp4", ".webm", ".mov"}
    filename = Path(file.filename or "video").name
    ext = Path(filename).suffix.lower()
    if file.content_type not in accepted_types or ext not in accepted_extensions:
        await file.close()
        raise HTTPException(status_code=415, detail="Upload MP4, WebM, or MOV video files only.")
    limit = MAX_UPLOAD_MB * 1024 * 1024
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    media_id = uuid.uuid4().hex
    destination = MEDIA_DIR / f"{media_id}{ext}"
    size = 0
    header = b""
    try:
        with destination.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"Video exceeds the {MAX_UPLOAD_MB} MB upload limit.")
                if len(header) < 16:
                    header += chunk[:16 - len(header)]
                out.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    valid_signature = (ext in {".mp4", ".mov"} and b"ftyp" in header[:12]) or (ext == ".webm" and header.startswith(bytes.fromhex("1a45dfa3")))
    if not valid_signature or size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=415, detail="The uploaded file does not appear to be a supported video.")
    expires = time.time() + MEDIA_TTL_SECONDS
    media_records[media_id] = {"path": str(destination), "filename": filename, "size": size, "content_type": file.content_type, "expires_at": expires}
    return {"id": media_id, "filename": filename, "size_bytes": size, "status": "ready", "download_url": f"/api/v1/media/{media_id}/download", "expires_in_seconds": MEDIA_TTL_SECONDS, "message": "Your authorized video file is ready for download."}

@app.get("/api/v1/media/{media_id}/download")
def download_uploaded_video(media_id: str):
    _cleanup_expired_media()
    record = media_records.get(media_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found or its temporary link has expired.")
    path = Path(record["path"])
    if not path.exists():
        media_records.pop(media_id, None)
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, media_type=record["content_type"], filename=record["filename"], headers={"Cache-Control": "no-store"})
