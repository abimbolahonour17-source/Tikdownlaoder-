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

def test_tiktok_download_not_enabled():
    response = client.post("/api/v1/download", json={"url": "https://www.tiktok.com/@creator/video/123"})
    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "DOWNLOAD_PROVIDER_NOT_CONFIGURED"

def test_authorized_video_upload_and_download():
    fake_mp4 = b"0000ftypisom" + b"sample-video"
    upload = client.post("/api/v1/media/upload", files={"file": ("clip.mp4", BytesIO(fake_mp4), "video/mp4")})
    assert upload.status_code == 200
    data = upload.json()
    assert data["status"] == "ready"
    download = client.get(data["download_url"])
    assert download.status_code == 200
    assert download.content == fake_mp4

def test_upload_rejects_non_video_mime():
    response = client.post("/api/v1/media/upload", files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")})
    assert response.status_code == 415

def test_ffmpeg_processing_endpoint(monkeypatch, tmp_path):
    import subprocess
    from pathlib import Path
    import app.main as main
    monkeypatch.setattr(main, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(main.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"processed-mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
    monkeypatch.setattr(main.subprocess, "run", fake_run)
    source = b"0000ftypisom" + b"source-video"
    upload = client.post("/api/v1/media/upload", files={"file": ("clip.mp4", BytesIO(source), "video/mp4")})
    assert upload.status_code == 200
    media_id = upload.json()["id"]
    processed = client.post(f"/api/v1/media/{media_id}/process?operation=compress&resolution=720")
    assert processed.status_code == 200
    result = processed.json()
    assert result["operation"] == "compress"
    assert result["resolution"] == "720"
    downloaded = client.get(result["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.content == b"processed-mp4"

def test_processing_requires_ffmpeg(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main.shutil, "which", lambda _name: None)
    source = b"0000ftypisom" + b"source-video"
    upload = client.post("/api/v1/media/upload", files={"file": ("clip.mp4", BytesIO(source), "video/mp4")})
    assert upload.status_code == 200
    processed = client.post(f"/api/v1/media/{upload.json()['id']}/process?operation=convert")
    assert processed.status_code == 503
