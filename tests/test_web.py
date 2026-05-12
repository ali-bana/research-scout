from fastapi.testclient import TestClient

from research_radar.app import create_app
from research_radar.config import get_settings


def test_login_page_renders(monkeypatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv(
        "ADMIN_PASSWORD_HASH",
        "pbkdf2_sha256$260000$lxPF9IATsBF4N4qL3cz5aw"
        "$X6hD4PkQ7yPbDNk9hwa2LVrGdi6HKYwmi2RGVT2HEMk",
    )
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/login")
    assert response.status_code == 200
    assert "Sign in" in response.text
