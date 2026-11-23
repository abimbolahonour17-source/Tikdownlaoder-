import os
import time
import uuid
import shutil
import subprocess
import threading
import socket
import ipaddress
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import persistence

APP_VERSION = "0.2.0"
ALLOWED_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
RATE_WINDOW_SECONDS = int(os.getenv("RATE_WINDOW_SECONDS", "60"))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "80"))
MEDIA_TTL_SECONDS = int(os.getenv("MEDIA_TTL_SECONDS", "3600"))
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/tmp/tikdownload-media"))
request_times: dict[str, deque[float]] = defaultdict(deque)
media_records: dict[str, dict] = {record['id']: record for record in persistence.list_media()}
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
    for record in persistence.list_media():
        media_id = record["id"]
        media_records[media_id] = record
        if record["expires_at"] <= now:
            try:
                Path(record["path"]).unlink(missing_ok=True)
            finally:
                media_records.pop(media_id, None)
                persistence.delete_media(media_id)

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
    database = "ok"
    queue = "local-thread"
    try:
        with persistence.connect() as db:
            db.execute("SELECT 1")
    except Exception:
        database = "unavailable"
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            from redis import Redis
            Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
            queue = "redis-ready"
        except Exception:
            queue = "redis-unavailable"
    return {"status": "ok" if database == "ok" else "degraded", "version": APP_VERSION, "database": database, "queue": queue}

@app.post("/api/v1/validate", response_model=LinkValidation)
def validate_link(body: LinkRequest):
    normalized = validate_tiktok_url(body.url)
    if not normalized:
        return LinkValidation(valid=False, message="Enter a valid HTTPS TikTok video link.")
    return LinkValidation(valid=True, normalized_url=normalized, message="TikTok URL format looks valid.")

def _is_public_https_media_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return False
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses:
            return False
        return all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (ValueError, OSError):
        return False

@app.post("/api/v1/download")
def download_video(body: LinkRequest):
    normalized = validate_tiktok_url(body.url)
    if not normalized:
        raise HTTPException(status_code=400, detail="Enter a valid HTTPS TikTok video link.")
    provider_url = os.getenv("TIKTOK_RETRIEVAL_API_URL", "").strip()
    provider_token = os.getenv("TIKTOK_RETRIEVAL_API_TOKEN", "").strip()
    if not provider_url or not provider_token:
        raise HTTPException(status_code=501, detail={"code": "DOWNLOAD_PROVIDER_NOT_CONFIGURED", "message": "URL retrieval requires a configured, authorized media provider. TikDownload does not scrape TikTok or bypass access controls."})
    import httpx
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=False) as client:
            provider_response = client.post(provider_url, json={"url": normalized}, headers={"Authorization": f"Bearer {provider_token}", "Accept": "application/json"})
            provider_response.raise_for_status()
            provider_data = provider_response.json()
            media_url = provider_data.get("download_url")
            if not isinstance(media_url, str) or not _is_public_https_media_url(media_url):
                raise HTTPException(status_code=502, detail="Provider returned an unsafe or invalid media URL.")
            filename = Path(str(provider_data.get("filename") or "tiktok-video.mp4")).name
            if not filename.lower().endswith((".mp4", ".webm", ".mov")):
                filename = "tiktok-video.mp4"
            media_id = uuid.uuid4().hex
            MEDIA_DIR.mkdir(parents=True, exist_ok=True)
            destination = MEDIA_DIR / f"{media_id}{Path(filename).suffix.lower()}"
            size = 0
            with client.stream("GET", media_url, follow_redirects=False) as stream:
                stream.raise_for_status()
                content_type = stream.headers.get("content-type", "").split(";")[0].lower()
                if not content_type.startswith("video/"):
                    raise HTTPException(status_code=502, detail="Provider media endpoint did not return a video.")
                limit = MAX_UPLOAD_MB * 1024 * 1024
                with destination.open("wb") as output:
                    for chunk in stream.iter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > limit:
                            raise HTTPException(status_code=413, detail=f"Retrieved video exceeds the {MAX_UPLOAD_MB} MB limit.")
                        output.write(chunk)
            expires = time.time() + MEDIA_TTL_SECONDS
            record = {"id": media_id, "path": str(destination), "filename": filename, "size": size, "content_type": content_type, "expires_at": expires}
            media_records[media_id] = record
            persistence.save_media(media_id, record)
            return {"id": media_id, "filename": filename, "size_bytes": size, "status": "ready", "download_url": f"/api/v1/media/{media_id}/download", "expires_in_seconds": MEDIA_TTL_SECONDS, "message": "Video retrieval completed through the configured provider."}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail="Configured media provider failed to retrieve the video.") from error

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
    record = {"id": media_id, "path": str(destination), "filename": filename, "size": size, "content_type": file.content_type, "expires_at": expires}
    media_records[media_id] = record
    persistence.save_media(media_id, record)
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
    persistence.update_job(job_id, status="running", message=job["message"])
    duration = _probe_duration(source["path"])
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        timeout_timer = threading.Timer(900, lambda: getattr(process, "kill", lambda: None)())
        timeout_timer.daemon = True
        timeout_timer.start()
        last_time = 0.0
        for line in process.stdout or []:
            line = line.strip()
            if line.startswith("out_time_ms="):
                try:
                    last_time = int(line.split("=", 1)[1]) / 1_000_000
                    if duration and duration > 0:
                        job["progress"] = min(99, max(1, int(last_time / duration * 100)))
                        persistence.update_job(job_id, progress=job['progress'])
                except (ValueError, IndexError):
                    pass
            elif line == "progress=end":
                job["progress"] = 99
                persistence.update_job(job_id, progress=99)
        return_code = process.wait(timeout=900)
        timeout_timer.cancel()
        if return_code != 0 or not output_path.exists() or output_path.stat().st_size == 0:
            output_path.unlink(missing_ok=True)
            job.update(status="failed", progress=0, message="Video processing failed. Try another video or preset.")
            persistence.update_job(job_id, status="failed", progress=0, message=job["message"])
            return
        expires = time.time() + MEDIA_TTL_SECONDS
        output_size = output_path.stat().st_size
        record = {"id": output_id, "path": str(output_path), "filename": f"tikdownload-{operation}.mp4", "size": output_size, "content_type": "video/mp4", "expires_at": expires}
        media_records[output_id] = record
        persistence.save_media(output_id, record)
        job.update(status="completed", progress=100, message="Processing complete.", output_id=output_id, filename=media_records[output_id]["filename"], size_bytes=output_size, download_url=f"/api/v1/media/{output_id}/download", expires_in_seconds=MEDIA_TTL_SECONDS, operation=operation, resolution=resolution, original_size_bytes=source["size"], size_change_bytes=output_size - source["size"])
        persistence.update_job(job_id, status="completed", progress=100, message="Processing complete.", output_id=output_id, filename=media_records[output_id]["filename"], size_bytes=output_size, download_url=f"/api/v1/media/{output_id}/download", expires_in_seconds=MEDIA_TTL_SECONDS, original_size_bytes=source["size"], size_change_bytes=output_size - source["size"])
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except Exception:
            pass
        output_path.unlink(missing_ok=True)
        job.update(status="failed", progress=0, message="Video processing took too long.")
        persistence.update_job(job_id, status="failed", progress=0, message=job["message"])
    except Exception:
        output_path.unlink(missing_ok=True)
        job.update(status="failed", progress=0, message="Video processing failed unexpectedly.")
        persistence.update_job(job_id, status="failed", progress=0, message=job["message"])

@app.post("/api/v1/media/{media_id}/process", status_code=202)
def process_uploaded_video(media_id: str, operation: str = "convert", resolution: str = "keep"):
    """Queue authorized uploaded media conversion/compression."""
    _cleanup_expired_media()
    source = media_records.get(media_id) or persistence.get_media(media_id)
    if not source:
        raise HTTPException(status_code=404, detail="Upload not found or expired.")
    if operation not in {"convert", "compress"}:
        raise HTTPException(status_code=400, detail="Choose convert or compress.")
    if resolution not in {"keep", "1080", "720", "480"}:
        raise HTTPException(status_code=400, detail="Unsupported resolution preset.")
    if not shutil.which("ffmpeg"):
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server.")
    job_id = uuid.uuid4().hex
    output_id = uuid.uuid4().hex
    output_path = MEDIA_DIR / f"{output_id}.mp4"
    job = {"id": job_id, "status": "queued", "progress": 0, "message": "Job queued.", "created_at": time.time(), "media_id": media_id, "operation": operation, "resolution": resolution}
    processing_jobs[job_id] = job
    persistence.create_job(job)
    try:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            from redis import Redis
            from rq import Queue
            redis_conn = Redis.from_url(redis_url)
            queue = Queue("video-processing", connection=redis_conn)
            queue.enqueue("app.tasks.process_media_job", job_id, source["path"], source["size"], output_id, str(output_path), operation, resolution, MEDIA_TTL_SECONDS, str(MEDIA_DIR), job_id=job_id, job_timeout=950, result_ttl=3600, failure_ttl=86400)
            job["queue"] = "redis"
        else:
            # Development fallback; durable records are retained, but local execution is process-bound.
            thread = threading.Thread(target=_run_processing_job, args=(job_id, source.copy(), output_id, output_path, [shutil.which("ffmpeg"), "-y", "-i", source["path"], "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", "-crf", "28" if operation == "compress" else "23"] + (["-vf", f"scale=-2:{int(resolution)}:force_original_aspect_ratio=decrease"] if resolution != "keep" else []) + [str(output_path)], operation, resolution), daemon=True)
            thread.start()
            job["queue"] = "local-thread"
    except Exception:
        persistence.update_job(job_id, status="failed", message="Could not enqueue video processing job.")
        raise HTTPException(status_code=503, detail="Processing queue is unavailable. Try again later.")
    return {"job_id": job_id, "status": "queued", "progress": 0, "message": "Processing job queued.", "status_url": f"/api/v1/jobs/{job_id}"}

@app.get("/api/v1/jobs/{job_id}")
def get_processing_job(job_id: str):
    job = persistence.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job not found.")
    if os.getenv("REDIS_URL"):
        try:
            from redis import Redis
            from rq.job import Job as RQJob
            rq_job = RQJob.fetch(job_id, connection=Redis.from_url(os.getenv("REDIS_URL")))
            rq_status = rq_job.get_status(refresh=True)
            if rq_status == "failed":
                persistence.update_job(job_id, status="failed", progress=0, message="Background worker failed. Please retry.")
            elif rq_status == "started" and job["status"] != "completed":
                persistence.update_job(job_id, status="running", message="Worker is processing the video.")
            job = persistence.get_job(job_id) or job
        except Exception:
            # SQLite remains the source of truth for status if Redis is temporarily unavailable.
            pass
    return {key: value for key, value in job.items() if key not in {"created_at", "media_id"}}

@app.get("/api/v1/media/{media_id}/download")
def download_uploaded_video(media_id: str):
    _cleanup_expired_media()
    record = media_records.get(media_id) or persistence.get_media(media_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found or its temporary link has expired.")
    path = Path(record["path"])
    if not path.exists():
        media_records.pop(media_id, None)
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, media_type=record["content_type"], filename=record["filename"], headers={"Cache-Control": "no-store"})
