import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/tmp/tikdownload-media"))
S3_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", os.getenv("S3_BUCKET", "")).strip()
S3_ENDPOINT_URL = os.getenv("SUPABASE_S3_ENDPOINT_URL", os.getenv("S3_ENDPOINT_URL", "")).strip()
S3_REGION = os.getenv("SUPABASE_S3_REGION", os.getenv("S3_REGION", "auto")).strip()
S3_ACCESS_KEY_ID = os.getenv("SUPABASE_S3_ACCESS_KEY_ID", os.getenv("S3_ACCESS_KEY_ID", "")).strip()
S3_SECRET_ACCESS_KEY = os.getenv("SUPABASE_S3_SECRET_ACCESS_KEY", os.getenv("S3_SECRET_ACCESS_KEY", "")).strip()
S3_ENABLED = bool(S3_BUCKET and S3_ENDPOINT_URL and S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY)

def _client():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=S3_ENDPOINT_URL, region_name=S3_REGION,
        aws_access_key_id=S3_ACCESS_KEY_ID, aws_secret_access_key=S3_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))

def _guess_content_type(path):
    ext = Path(path).suffix.lower()
    return {".mp4":"video/mp4",".webm":"video/webm",".mov":"video/quicktime"}.get(ext,"application/octet-stream")

def store_file(source, key):
    source = Path(source)
    if S3_ENABLED:
        _client().upload_file(str(source), S3_BUCKET, key, ExtraArgs={"ContentType": _guess_content_type(source)})
        return f"s3://{S3_BUCKET}/{key}"
    destination = MEDIA_DIR / key
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return str(destination)

def localize(stored_path, destination):
    destination = Path(destination)
    if stored_path.startswith("s3://"):
        parsed = urlparse(stored_path)
        _client().download_file(parsed.netloc, parsed.path.lstrip("/"), str(destination))
    else:
        shutil.copyfile(stored_path, destination)
    return destination

def delete_file(stored_path):
    if stored_path.startswith("s3://"):
        parsed = urlparse(stored_path)
        _client().delete_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
    else:
        Path(stored_path).unlink(missing_ok=True)

def exists(stored_path):
    if stored_path.startswith("s3://"):
        parsed = urlparse(stored_path)
        try:
            _client().head_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
            return True
        except Exception:
            return False
    return Path(stored_path).exists()

def temporary_path(suffix=".mp4"):
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    Path(name).unlink(missing_ok=True)
    return Path(name)


def presigned_download_url(stored_path, filename, expires_seconds=3600):
    """Return a short-lived direct download URL for S3-compatible storage."""
    if not S3_ENABLED or not stored_path.startswith("s3://"):
        return None
    parsed = urlparse(stored_path)
    return _client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": parsed.netloc,
            "Key": parsed.path.lstrip("/"),
            "ResponseContentDisposition": f'attachment; filename="{Path(filename).name}"',
        },
        ExpiresIn=max(60, min(int(expires_seconds), 3600)),
    )


def presigned_download_url(stored_path, filename, expires_seconds=3600):
    """Return a temporary direct S3 download URL when configured."""
    if not S3_ENABLED or not stored_path.startswith("s3://"):
        return None
    parsed = urlparse(stored_path)
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": parsed.netloc, "Key": parsed.path.lstrip("/"),
               "ResponseContentDisposition": f'attachment; filename="{Path(filename).name}"'},
        ExpiresIn=max(60, min(int(expires_seconds), 604800)),
    )
