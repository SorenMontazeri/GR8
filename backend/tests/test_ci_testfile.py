from fastapi.testclient import TestClient
from test_ci import app

client = TestClient(app)

def test_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
