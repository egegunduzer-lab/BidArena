"""Açık artırma kapanışı ve kazananın belirlenmesi (AuctionCloser, ADR-03)."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import Auction
from app.services.auction_service import AuctionCloser
from app.services.bid_service import BidService
from app.services.errors import AuctionNotActive
from helpers import (
    CAN_AUTO,
    ELIF,
    LIVE_AUCTION,
    MEHMET,
    SCHEDULED_AUCTION,
    SELLER,
    UNVERIFIED,
    auction_row,
    run_sql,
    set_end_in,
)


def appointments(auction_id=LIVE_AUCTION):
    return run_sql(
        "SELECT buyer_id, seller_id, agreed_price, status FROM appointments WHERE auction_id = :a",
        a=auction_id,
    ).all()


def close_notifications(auction_id=LIVE_AUCTION):
    rows = run_sql(
        "SELECT user_id, type FROM notifications "
        "WHERE type IN ('AUCTION_WON', 'AUCTION_LOST', 'AUCTION_ENDED') "
        "AND (payload->>'auction_id')::int = :a",
        a=auction_id,
    ).all()
    return {(r.user_id, r.type) for r in rows}


# ------------------------------------------------------------ kazanan belirleme
def test_expired_auction_closes_with_highest_bidder_as_winner():
    set_end_in(-1)
    run = AuctionCloser().run_once()

    assert [c.auction_id for c in run.closed] == [LIVE_AUCTION]
    closed = run.closed[0]
    assert closed.winner_id == CAN_AUTO
    assert closed.final_price == 11500

    row = run_sql("SELECT status, winner_id FROM auctions WHERE id = 1").one()
    assert (row.status, row.winner_id) == ("CLOSED", CAN_AUTO)
    assert run_sql("SELECT status FROM listings WHERE id = 1").scalar_one() == "CLOSED"


def test_winner_gets_proposed_appointment_at_winning_price():
    set_end_in(-1)
    closed = AuctionCloser().run_once().closed[0]

    assert appointments() == [(CAN_AUTO, SELLER, 11500, "PROPOSED")]
    assert closed.appointment_id is not None


def test_close_notifies_winner_seller_losers_and_watchers():
    set_end_in(-1)
    AuctionCloser().run_once()
    assert close_notifications() == {
        (CAN_AUTO, "AUCTION_WON"),
        (SELLER, "AUCTION_ENDED"),
        (MEHMET, "AUCTION_LOST"),
        (ELIF, "AUCTION_LOST"),          # hem teklif verdi hem takip ediyor: tek bildirim
        (UNVERIFIED, "AUCTION_ENDED"),   # sadece takip ediyor
    }


def test_close_deactivates_auto_bids_and_writes_audit_log():
    set_end_in(-1)
    AuctionCloser().run_once()
    active = run_sql(
        "SELECT count(*) FROM auto_bid_limits WHERE auction_id = 1 AND is_active"
    ).scalar_one()
    assert active == 0
    log = run_sql(
        "SELECT data FROM audit_logs WHERE action = 'AUCTION_CLOSED' AND entity_id = 1"
    ).scalar_one()
    assert log["winner_id"] == CAN_AUTO and log["price"] == 11500


def test_auction_without_bids_closes_without_winner():
    run_sql(
        "UPDATE auctions SET start_time = clock_timestamp() - interval '2 days', "
        "end_time = clock_timestamp() - interval '1 second' WHERE id = :a",
        a=SCHEDULED_AUCTION,
    )
    closed = AuctionCloser().run_once().closed

    assert [(c.auction_id, c.winner_id, c.final_price) for c in closed] == [
        (SCHEDULED_AUCTION, None, None)
    ]
    assert appointments(SCHEDULED_AUCTION) == []
    # Satılmadı: ilan aktif kalır, yeniden açık artırmaya çıkarılabilir.
    assert run_sql("SELECT status FROM listings WHERE id = 4").scalar_one() == "ACTIVE"


def test_running_auction_is_not_closed():
    set_end_in(60)
    assert AuctionCloser().run_once().closed == []
    assert auction_row().status == "ACTIVE"


def test_scheduled_auction_starts_when_start_time_passes():
    run_sql(
        "UPDATE auctions SET start_time = clock_timestamp() - interval '1 second' WHERE id = :a",
        a=SCHEDULED_AUCTION,
    )
    run = AuctionCloser().run_once()
    assert run.started == [SCHEDULED_AUCTION]
    assert auction_row(SCHEDULED_AUCTION).status == "ACTIVE"


# ------------------------------------------------------------ kapanış sonrası
def test_bid_after_close_is_rejected(db):
    set_end_in(-1)
    AuctionCloser().run_once()
    with pytest.raises(AuctionNotActive, match="kapandı"):
        BidService(db).place_bid(LIVE_AUCTION, MEHMET, 20000, "late")


def test_closing_twice_is_harmless():
    set_end_in(-1)
    closer = AuctionCloser()
    assert len(closer.run_once().closed) == 1
    assert closer.run_once().closed == []
    assert len(appointments()) == 1


# ------------------------------------------------------------ yarış durumları
def test_closer_skips_auction_locked_by_bid_and_respects_extension():
    """Teklif satırı kilitliyken kapanış beklemez; teklif süreyi uzatırsa kapatmaz.

    Bitişten hemen önce gelen teklifin işlenmesini taklit eder: teklif işlemi
    satırı kilitler ve bitişi uzatır, henüz commit etmemiştir.
    """
    set_end_in(-1)
    bid_tx = SessionLocal()
    try:
        bid_tx.execute(select(Auction).where(Auction.id == LIVE_AUCTION).with_for_update())
        bid_tx.execute(text(
            "UPDATE auctions SET end_time = clock_timestamp() + interval '2 minutes' WHERE id = 1"
        ))

        # Kilit tutulurken: kapanış bu turu atlar (beklemez, hata vermez).
        assert AuctionCloser().close_auction(LIVE_AUCTION) is None

        bid_tx.commit()
    finally:
        bid_tx.close()

    # Teklif commit edildi ve süre uzadı. Kapanış bu açık artırmayı süre
    # uzamadan önce "süresi dolmuş" diye listeye almış olsa bile, kilidi
    # aldıktan sonra bitişi yeniden kontrol eder ve kapatmaz.
    assert AuctionCloser().close_auction(LIVE_AUCTION) is None
    assert AuctionCloser().run_once().closed == []
    assert auction_row().status == "ACTIVE"


def test_concurrent_closers_close_exactly_once():
    """Birden fazla sunucu süreci aynı anda kapanış çalıştırsa da tek kapanış olur."""
    set_end_in(-1)
    barrier = threading.Barrier(10)

    def close():
        barrier.wait()
        return AuctionCloser().close_auction(LIVE_AUCTION)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: close(), range(10)))

    assert sum(r is not None for r in results) == 1
    assert len(appointments()) == 1
    assert run_sql(
        "SELECT count(*) FROM audit_logs WHERE action = 'AUCTION_CLOSED' AND entity_id = 1"
    ).scalar_one() == 1


# ------------------------------------------------------------ zamanlayıcı
def test_scheduler_closes_auction_and_broadcasts(monkeypatch):
    monkeypatch.setenv("AUCTION_CLOSER_ENABLED", "1")
    monkeypatch.setenv("AUCTION_CLOSER_INTERVAL", "0.1")
    set_end_in(1)

    from main import app

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/auctions/{LIVE_AUCTION}") as ws:
            assert ws.receive_json()["event"] == "SNAPSHOT"
            event = ws.receive_json()

    assert event["event"] == "AUCTION_CLOSED"
    assert event["winner_id"] == CAN_AUTO
    assert event["final_price"] == 11500
    assert auction_row().status == "CLOSED"
