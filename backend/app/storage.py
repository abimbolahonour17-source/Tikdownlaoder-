"""Vercel Blob-backed media storage. No local or S3 fallback is permitted."""
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager

BLOB_ACCESS = os.getenv("BLOB_ACCESS", "public").strip().lower()
if BLOB_ACCESS not in {"public", "private"}:
    raise RuntimeError("BLOB_ACCESS must be public or private.")

def _blob():
    try:
        from vercel.blob import sync as blob
    except ImportError as exc:
        raise RuntimeError("Install the vercel-blob package to use Vercel Blob storage.") from exc
    if not (os.getenv("BLOB_READ_WRITE_TOKEN") or os.getenv("VERCEL_BLOB_READ_WRITE_TOKEN") or os.getenv("VERCEL_OIDC_TOKEN")):
        raise RuntimeError("Vercel Blob credentials are missing. Configure BLOB_READ_WRITE_TOKEN.")
    return blob

def require_external_storage():
    _blob()

def _guess_content_type(path):
    ext = Path(path).suffix.lower()
    return {".mp4":"video/mp4", ".webm":"video/webm", ".mov":"video/quicktime"}.get(ext, "application/octet-stream")

def store_file(source, key):
    source = Path(source)
    with source.open("rb") as stream:
        result = _blob().put_blob(key, stream, access=BLOB_ACCESS, content_type=_guess_content_type(source), content_length=source.stat().st_size, add_random_suffix=True)
    return result.url

def delete_file(stored_path):
    if not stored_path.startswith("https://"):
        raise RuntimeError("Invalid Vercel Blob URL.")
    _blob().delete_blob(stored_path)

def exists(stored_path):
    try:
        return bool(_blob().head_blob(stored_path).size is not None)
    except Exception:
        return False

@contextmanager
def stream_file(stored_path):
    if not stored_path.startswith("https://"):
        raise RuntimeError("Invalid Vercel Blob URL.")
    with _blob().stream_blob(stored_path, access=BLOB_ACCESS) as stream:
        yield stream

def temporary_path(suffix=".mp4"):
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    Path(name).unlink(missing_ok=True)
    return Path(name)

def localize(stored_path, destination):
    """Legacy processing adapter; local processing remains disabled on Vercel."""
    destination = Path(destination)
    with stream_file(stored_path) as stream, destination.open("wb") as output:
        for chunk in stream:
            output.write(chunk)
    return destination

def presigned_download_url(stored_path, filename, expires_seconds=3600):
    # Do not expose the underlying Blob URL. The API's random-id route enforces expiry.
    return None
