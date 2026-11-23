import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import persistence, storage

def process_media_job(job_id, source_path, source_size, output_id, output_path, operation, resolution, ttl_seconds, media_dir):
    job = persistence.get_job(job_id)
    if not job:
        return {"status": "missing"}
    persistence.update_job(job_id, status="running", message="FFmpeg is processing your video.", progress=0)
    source_local = storage.temporary_path(Path(source_path).suffix or ".mp4")
    storage.localize(source_path, source_local)
    source_path = str(source_local)
    duration = None
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", source_path], capture_output=True, text=True, timeout=20)
            if probe.returncode == 0 and probe.stdout.strip():
                duration = float(probe.stdout.strip())
        except Exception:
            pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        persistence.update_job(job_id, status="failed", progress=0, message="FFmpeg is not installed on the worker.")
        source_local.unlink(missing_ok=True)
        return {"status": "failed"}
    command = [ffmpeg, "-y", "-i", source_path, "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", "-crf", "28" if operation == "compress" else "23"]
    if resolution != "keep":
        command += ["-vf", f"scale=-2:{int(resolution)}:force_original_aspect_ratio=decrease"]
    command.append(output_path)
    process = None
    timer = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        timer = threading.Timer(900, process.kill)
        timer.daemon = True
        timer.start()
        for line in process.stdout or []:
            if line.startswith("out_time_ms=") and duration and duration > 0:
                try:
                    pct = min(99, max(1, int(int(line.split("=", 1)[1]) / 1000000 / duration * 100)))
                    persistence.update_job(job_id, progress=pct)
                except (ValueError, IndexError):
                    pass
            elif line.strip() == "progress=end":
                persistence.update_job(job_id, progress=99)
        code = process.wait()
        if timer:
            timer.cancel()
        output = Path(output_path)
        if code != 0 or not output.exists() or output.stat().st_size <= 0:
            persistence.update_job(job_id, status="failed", progress=0, message="Video processing failed. Try another video or preset.")
            return {"status": "failed"}
        size = output.stat().st_size
        expires = time.time() + ttl_seconds
        stored_output = storage.store_file(output, f"media/{output_id}.mp4")
        persistence.save_media(output_id, {"path": stored_output, "filename": f"tikdownload-{operation}.mp4", "size": size, "content_type": "video/mp4", "expires_at": expires})
        persistence.update_job(job_id, status="completed", progress=100, message="Processing complete.", output_id=output_id, filename=f"tikdownload-{operation}.mp4", size_bytes=size, original_size_bytes=source_size, size_change_bytes=size-source_size, download_url=f"/api/v1/media/{output_id}/download", expires_in_seconds=ttl_seconds)
        return {"status": "completed", "output_id": output_id}
    except Exception:
        if timer:
            timer.cancel()
        if process:
            try: process.kill()
            except Exception: pass
        persistence.update_job(job_id, status="failed", progress=0, message="Video processing failed or timed out.")
        return {"status": "failed"}
    finally:
        if timer:
            timer.cancel()
        source_local.unlink(missing_ok=True)
        Path(output_path).unlink(missing_ok=True)
