import os
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

APP_VERSION = "0.1.0"
ALLOWED_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
RATE_WINDOW_SECONDS = int(os.getenv("RATE_WINDOW_SECONDS", "60"))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
request_times: dict[str, deque[float]] = defaultdict(deque)

app = FastAPI(
    title="TikDownload API",
    description="URL validation API for TikDownload. Video retrieval is not implemented.",
    version=APP_VERSION,
)

allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5500").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

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
        if parsed.scheme != "https" or host not in ALLOWED_HOSTS:
            return None
        if not parsed.path or parsed.path == "/":
            return None
        return parsed.geturl()
    except (ValueError, TypeError):
        return None

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
    normalized = validate_tiktok_url(body.url)
    if not normalized:
        raise HTTPException(status_code=400, detail="Enter a valid HTTPS TikTok video link.")
    raise HTTPException(
        status_code=501,
        detail={
            "code": "DOWNLOAD_PROVIDER_NOT_CONFIGURED",
            "message": "Link validation is available, but video retrieval is not configured. Use TikTok's built-in save option or a permitted download source.",
        },
    )
