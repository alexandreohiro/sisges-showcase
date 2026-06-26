from fastapi.testclient import TestClient

from apps.web.app import app


def test_app_imports_and_healthcheck_works():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "SisGeS"
    assert payload["status"] == "ok"
    assert payload["database"]["status"] == "ok"


def test_liveness_check_works():
    client = TestClient(app)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
