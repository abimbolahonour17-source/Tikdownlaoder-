import os
import time
import uuid
import shutil
import subprocess
import threading
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
processing_jobs: dict[str, dict] = {}

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

def _probe_duration(path: str) -> float | None:
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    try:
        result = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True, timeout=20, check=False)
        return float(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None
    except Exception:
        return None

def _run_processing_job(job_id: str, source: dict, output_id: str, output_path: Path, command: list[str], operation: str, resolution: str):
    job = processing_jobs[job_id]
    job["status"] = "running"
    job["message"] = "FFmpeg is processing your video."
    duration = _probe_duration(source["path"])
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        last_time = 0.0
        for line in process.stdout or []:
            line = line.strip()
            if line.startswith("out_time_ms="):
                try:
                    last_time = int(line.split("=", 1)[1]) / 1_000_000
                    if duration and duration > 0:
                        job["progress"] = min(99, max(1, int(last_time / duration * 100)))
                except (ValueError, IndexError):
                    pass
            elif line == "progress=end":
                job["progress"] = 99
        return_code = process.wait(timeout=900)
        if return_code != 0 or not output_path.exists() or output_path.stat().st_size == 0:
            output_path.unlink(missing_ok=True)
            job.update(status="failed", progress=0, message="Video processing failed. Try another video or preset.")
            return
        expires = time.time() + MEDIA_TTL_SECONDS
        output_size = output_path.stat().st_size
        media_records[output_id] = {"path": str(output_path), "filename": f"tikdownload-{operation}.mp4", "size": output_size, "content_type": "video/mp4", "expires_at": expires}
        job.update(status="completed", progress=100, message="Processing complete.", output_id=output_id, filename=media_records[output_id]["filename"], size_bytes=output_size, download_url=f"/api/v1/media/{output_id}/download", expires_in_seconds=MEDIA_TTL_SECONDS, operation=operation, resolution=resolution, original_size_bytes=source["size"], size_change_bytes=output_size - source["size"])
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except Exception:
            pass
        output_path.unlink(missing_ok=True)
        job.update(status="failed", progress=0, message="Video processing took too long.")
    except Exception:
        output_path.unlink(missing_ok=True)
        job.update(status="failed", progress=0, message="Video processing failed unexpectedly.")

@app.post("/api/v1/media/{media_id}/process", status_code=202)
def process_uploaded_video(media_id: str, operation: str = "convert", resolution: str = "keep"):
    """Queue authorized uploaded media conversion/compression as a background job."""
    _cleanup_expired_media()
    source = media_records.get(media_id)
    if not source:
        raise HTTPException(status_code=404, detail="Upload not found or expired.")
    if operation not in {"convert", "compress"}:
        raise HTTPException(status_code=400, detail="Choose convert or compress.")
    if resolution not in {"keep", "1080", "720", "480"}:
        raise HTTPException(status_code=400, detail="Unsupported resolution preset.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server.")
    job_id = uuid.uuid4().hex
    output_id = uuid.uuid4().hex
    output_path = MEDIA_DIR / f"{output_id}.mp4"
    command = [ffmpeg, "-y", "-i", source["path"], "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats"]
    command += ["-crf", "28" if operation == "compress" else "23"]
    if resolution != "keep":
        command += ["-vf", f"scale=-2:{int(resolution)}:force_original_aspect_ratio=decrease"]
    command += [str(output_path)]
    processing_jobs[job_id] = {"id": job_id, "status": "queued", "progress": 0, "message": "Job queued.", "created_at": time.time(), "media_id": media_id, "operation": operation, "resolution": resolution}
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    thread = threading.Thread(target=_run_processing_job, args=(job_id, source.copy(), output_id, output_path, command, operation, resolution), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "queued", "progress": 0, "message": "Processing job queued.", "status_url": f"/api/v1/jobs/{job_id}"}

@app.get("/api/v1/jobs/{job_id}")
def get_processing_job(job_id: str):
    job = processing_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job not found.")
    return {key: value for key, value in job.items() if key not in {"created_at", "media_id"}}

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
