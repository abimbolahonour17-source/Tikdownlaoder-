from io import BytesIO
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_valid_tiktok_url():
    response = client.post("/api/v1/validate", json={"url": "https://www.tiktok.com/@creator/video/123456789"})
    assert response.status_code == 200
    assert response.json()["valid"] is True

def test_reject_non_tiktok_host():
    response = client.post("/api/v1/validate", json={"url": "https://example.com/video"})
    assert response.status_code == 200
    assert response.json()["valid"] is False

def test_reject_http_url():
    response = client.post("/api/v1/validate", json={"url": "http://www.tiktok.com/@creator/video/123"})
    assert response.status_code == 200
    assert response.json()["valid"] is False

def test_tiktok_download_provider_key_missing(monkeypatch):
    monkeypatch.delenv("GETINSAVER_API_KEY", raising=False)
    response = client.post("/api/v1/download", json={"url": "https://www.tiktok.com/@creator/video/123"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "RETRIEVAL_PROVIDER_KEY_MISSING"

def test_tiktok_download_uses_getinsaver_provider(monkeypatch, tmp_path):
    import httpx
    import app.main as main
    monkeypatch.setenv("GETINSAVER_API_KEY", "test-key")
    monkeypatch.setattr(main, "_is_public_https_media_url", lambda url: True)
    monkeypatch.setattr(main.storage, "MEDIA_DIR", tmp_path)
    video_bytes = b"fake-provider-video"
    class ProviderResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"ok": True, "items": [{"type": "video", "url": "https://cdn.example/video.mp4"}]}
    class MediaStream:
        headers = {"content-type": "video/mp4"}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_bytes(self, chunk_size):
            yield video_bytes
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json, headers):
            assert url == "https://developers.getinsaver.com/v1/resolve"
            assert json["service"] == "tiktok"
            assert headers["Authorization"] == "Bearer test-key"
            return ProviderResponse()
        def stream(self, *args, **kwargs): return MediaStream()
    monkeypatch.setattr(httpx, "Client", FakeClient)
    response = client.post("/api/v1/download", json={"url": "https://www.tiktok.com/@creator/video/123"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["size_bytes"] == len(video_bytes)
    assert client.get(data["download_url"]).content == video_bytes


def test_authorized_video_upload_and_download():
    fake_mp4 = b"0000ftypisom" + b"sample-video"
    upload = client.post("/api/v1/media/upload", files={"file": ("clip.mp4", BytesIO(fake_mp4), "video/mp4")})
    assert upload.status_code == 200
    data = upload.json()
    assert data["status"] == "ready"
    download = client.get(data["download_url"])
    assert download.status_code == 200
    assert download.content == fake_mp4
    import app.main as main
    assert main.persistence.get_media(data["id"])["filename"] == "clip.mp4"

def test_upload_rejects_non_video_mime():
    response = client.post("/api/v1/media/upload", files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")})
    assert response.status_code == 415

def test_ffmpeg_processing_endpoint(monkeypatch, tmp_path):
    import time
    import subprocess
    from pathlib import Path
    import app.main as main
    monkeypatch.setattr(main, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(main.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    class FakeProcess:
        def __init__(self, command, **kwargs):
            Path(command[-1]).write_bytes(b"processed-mp4")
            self.stdout = iter(["out_time_ms=5000000\n", "progress=end\n"])
        def wait(self, timeout=None):
            return 0
    monkeypatch.setattr(main.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(main.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="5.0\n", stderr=""))
    source = b"0000ftypisom" + b"source-video"
    upload = client.post("/api/v1/media/upload", files={"file": ("clip.mp4", BytesIO(source), "video/mp4")})
    assert upload.status_code == 200
    media_id = upload.json()["id"]
    queued = client.post(f"/api/v1/media/{media_id}/process?operation=compress&resolution=720")
    assert queued.status_code == 202
    job_id = queued.json()["job_id"]
    deadline = time.time() + 2
    status = {}
    while time.time() < deadline:
        status_response = client.get(f"/api/v1/jobs/{job_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert status["status"] == "completed"
    assert status["progress"] == 100
    assert status["operation"] == "compress"
    assert status["resolution"] == "720"
    assert status["original_size_bytes"] == len(source)
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "completed"
    downloaded = client.get(status["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.content == b"processed-mp4"

def test_processing_job_not_found():
    response = client.get("/api/v1/jobs/no-such-job")
    assert response.status_code == 404

def test_processing_requires_ffmpeg(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main.shutil, "which", lambda _name: None)
    source = b"0000ftypisom" + b"source-video"
    upload = client.post("/api/v1/media/upload", files={"file": ("clip.mp4", BytesIO(source), "video/mp4")})
    assert upload.status_code == 200
    processed = client.post(f"/api/v1/media/{upload.json()['id']}/process?operation=convert")
    assert processed.status_code == 503

def test_provider_media_url_rejects_private_addresses(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))])
    assert main._is_public_https_media_url("https://localhost/video.mp4") is False

def test_provider_media_url_requires_https():
    import app.main as main
    assert main._is_public_https_media_url("http://example.com/video.mp4") is False
