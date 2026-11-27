from fastapi.testclient import TestClient

from main import app
from app.models import TrustEvent

client = TestClient(app)


def test_get_user_trust_score():
    response = client.get("/api/users/1/trust")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 1
    assert data["trust_score"] == 0.0


def test_buyer_score_uses_verified_event_points():
    response = client.get("/api/users/8/trust?party=BUYER")
    assert response.status_code == 200
    assert response.json()["trust_score"] == 10.0


def test_paid_subscription_does_not_add_to_seller_score():
    # Seed'de kullanıcı 3'ün PROFESSIONAL aboneliği ve doğrulanmış +10 seller olayı var.
    response = client.get("/api/users/3/trust?party=SELLER")
    assert response.status_code == 200
    assert response.json()["trust_score"] == 10.0


def test_unverified_event_does_not_affect_score():
    # Seed'deki kullanıcının doğrulanmamış -20 BUYER olayı puana katılmamalı.
    response = client.get("/api/users/5/trust?party=BUYER")
    assert response.status_code == 200
    assert response.json()["trust_score"] == 0.0


def test_verified_negative_points_are_counted(db):
    db.add(
        TrustEvent(
            user_id=5,
            party="BUYER",
            type="NO_SHOW",
            points=-20,
            verified=True,
        )
    )
    db.commit()

    response = client.get("/api/users/5/trust?party=BUYER")
    assert response.status_code == 200
    assert response.json()["trust_score"] == -20.0
