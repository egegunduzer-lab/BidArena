from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_get_user_trust_score():
    response = client.get("/api/users/1/trust")
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "trust_score" in data
    assert data["user_id"] == 1