"""REST uç noktaları ve WebSocket yayını (entegrasyon testleri)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from helpers import CLOSED_AUCTION, ELIF, LIVE_AUCTION, MEHMET, disable_auto_bids
from main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def bid(client, amount, user=ELIF, key="api-1", auction=LIVE_AUCTION):
    return client.post(
        f"/api/auctions/{auction}/bids",
        json={"amount": amount},
        headers={"X-User-Id": str(user), "Idempotency-Key": key},
    )


def test_place_bid_returns_201_and_new_state(client):
    disable_auto_bids()
    r = bid(client, 11750)
    assert r.status_code == 201
    body = r.json()
    assert body["current_price"] == 11750
    assert body["highest_bidder_id"] == ELIF
    assert body["duplicate"] is False


def test_retry_returns_200_with_same_state(client):
    disable_auto_bids()
    bid(client, 11750)
    r = bid(client, 11750)
    assert r.status_code == 200
    assert r.json()["duplicate"] is True


def test_low_bid_returns_422_with_minimum(client):
    r = bid(client, 11600)
    assert r.status_code == 422
    assert r.json()["detail"] == {
        "code": "BID_TOO_LOW",
        "message": "Teklif en az 11750 TL olmalı.",
        "min_amount": 11750,
    }


def test_closed_auction_returns_409(client):
    r = bid(client, 99999, auction=CLOSED_AUCTION)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "AUCTION_NOT_ACTIVE"


def test_missing_idempotency_key_rejected(client):
    r = client.post(
        f"/api/auctions/{LIVE_AUCTION}/bids", json={"amount": 11750}, headers={"X-User-Id": "6"}
    )
    assert r.status_code == 422


def test_non_integer_or_negative_amount_rejected(client):
    assert bid(client, -5).status_code == 422
    assert bid(client, 11750.5).status_code == 422


def test_get_auction_state(client):
    r = client.get(f"/api/auctions/{LIVE_AUCTION}")
    assert r.status_code == 200
    body = r.json()
    assert body["current_price"] == 11500
    assert body["min_next_bid"] == 11750
    assert body["status"] == "ACTIVE"
    assert len(body["bids"]) == 4
    assert "server_time" in body


def test_auction_state_includes_listing_info(client):
    body = client.get(f"/api/auctions/{LIVE_AUCTION}").json()
    assert body["listing"]["title"] == "Trek Marlin 7 Dağ Bisikleti"
    assert body["listing"]["defects"] == "Sağ vites kolunda çizik."
    assert body["listing"]["seller_id"] == 2
    assert body["winner_id"] is None


def test_list_auctions_live_first(client):
    r = client.get("/api/auctions")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 5
    assert rows[0]["auction_id"] == LIVE_AUCTION
    assert rows[0]["status"] == "ACTIVE"
    assert rows[0]["bid_count"] == 4
    assert [row["status"] for row in rows] == ["ACTIVE", "SCHEDULED", "CLOSED", "CLOSED", "CLOSED"]


def test_auto_bid_endpoint(client):
    r = client.put(
        f"/api/auctions/{LIVE_AUCTION}/auto-bid",
        json={"max_amount": 12500},
        headers={"X-User-Id": str(ELIF)},
    )
    assert r.status_code == 200
    assert r.json()["current_price"] == 12750


def test_websocket_receives_snapshot_then_new_bid(client):
    with client.websocket_connect(f"/ws/auctions/{LIVE_AUCTION}") as ws:
        snapshot = ws.receive_json()
        assert snapshot["event"] == "SNAPSHOT"
        assert snapshot["current_price"] == 11500

        r = bid(client, 11750, user=MEHMET)
        assert r.status_code == 201

        event = ws.receive_json()
        assert event["event"] == "NEW_BID"
        assert event["current_price"] == 12000  # Mehmet 11.750, Can otomatik 12.000
        assert [b["is_auto"] for b in event["bids"]] == [False, True]


def test_websocket_ping(client):
    with client.websocket_connect(f"/ws/auctions/{LIVE_AUCTION}") as ws:
        ws.receive_json()
        ws.send_text("ping")
        assert ws.receive_json() == {"event": "PONG"}


def test_websocket_unknown_auction_is_closed(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/auctions/999") as ws:
            ws.receive_json()
