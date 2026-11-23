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

def test_download_endpoint_not_configured():
    response = client.post("/api/v1/download", json={"url": "https://www.tiktok.com/@creator/video/123"})
    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "DOWNLOAD_PROVIDER_NOT_CONFIGURED"
