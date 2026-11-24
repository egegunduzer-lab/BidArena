"""Teklif motorunun iş kuralları (BidService, gerçek PostgreSQL üzerinde)."""
from datetime import timedelta

import pytest

from app.services.bid_service import BidService
from app.services.errors import (
    AuctionNotActive,
    AuctionNotFound,
    BidNotAllowed,
    BidTooLow,
    IdempotencyConflict,
)
from helpers import (
    CAN_AUTO,
    CLOSED_AUCTION,
    ELIF,
    LIVE_AUCTION,
    MEHMET,
    RESTRICTED,
    SCHEDULED_AUCTION,
    SELLER,
    UNVERIFIED,
    auction_row,
    bid_count,
    disable_auto_bids,
    run_sql,
    set_end_in,
)


# ------------------------------------------------------------ geçerli teklif
def test_valid_bid_updates_price_and_leader(db):
    disable_auto_bids()
    outcome = BidService(db).place_bid(LIVE_AUCTION, ELIF, 11750, "k1")

    assert outcome.current_price == 11750
    assert outcome.highest_bidder_id == ELIF
    assert outcome.min_next_bid == 12000
    assert [b.amount for b in outcome.bids] == [11750]
    row = auction_row()
    assert row.current_price == 11750
    assert row.highest_bid_id == outcome.bids[0].id


def test_outbid_user_gets_notification(db):
    disable_auto_bids()
    BidService(db).place_bid(LIVE_AUCTION, ELIF, 11750, "k1")
    n = run_sql(
        "SELECT count(*) FROM notifications WHERE user_id = :u AND type = 'OUTBID' "
        "AND (payload->>'new_price')::int = 11750",
        u=CAN_AUTO,
    ).scalar_one()
    assert n == 1


# ------------------------------------------------------------ minimum artış
def test_bid_below_min_increment_rejected(db):
    with pytest.raises(BidTooLow) as err:
        BidService(db).place_bid(LIVE_AUCTION, ELIF, 11600, "k1")
    assert err.value.min_amount == 11750
    assert auction_row().current_price == 11500


def test_first_bid_must_be_at_least_start_price(db):
    run_sql("UPDATE auctions SET start_time = clock_timestamp() - interval '1 minute' WHERE id = :a",
            a=SCHEDULED_AUCTION)
    with pytest.raises(BidTooLow) as err:
        BidService(db).place_bid(SCHEDULED_AUCTION, MEHMET, 29000, "k1")
    assert err.value.min_amount == 30000

    outcome = BidService(db).place_bid(SCHEDULED_AUCTION, MEHMET, 30000, "k2")
    assert outcome.current_price == 30000
    assert auction_row(SCHEDULED_AUCTION).status == "ACTIVE"


# ------------------------------------------------------------ kim teklif verebilir
def test_seller_cannot_bid_on_own_listing(db):
    with pytest.raises(BidNotAllowed):
        BidService(db).place_bid(LIVE_AUCTION, SELLER, 12000, "k1")


def test_restricted_user_cannot_bid(db):
    with pytest.raises(BidNotAllowed, match="kısıtlı"):
        BidService(db).place_bid(LIVE_AUCTION, RESTRICTED, 12000, "k1")


def test_unverified_account_has_bid_limit(db):
    disable_auto_bids()
    with pytest.raises(BidNotAllowed, match="Doğrulanmamış"):
        BidService(db).place_bid(LIVE_AUCTION, UNVERIFIED, 25000, "k1")
    assert BidService(db).place_bid(LIVE_AUCTION, UNVERIFIED, 12000, "k2").current_price == 12000


def test_leader_cannot_outbid_themselves(db):
    with pytest.raises(BidNotAllowed, match="zaten sizde"):
        BidService(db).place_bid(LIVE_AUCTION, CAN_AUTO, 11750, "k1")


def test_unknown_auction(db):
    with pytest.raises(AuctionNotFound):
        BidService(db).place_bid(999, ELIF, 11750, "k1")


# ------------------------------------------------------------ süre ve kapanış
def test_closed_auction_rejects_bids(db):
    with pytest.raises(AuctionNotActive):
        BidService(db).place_bid(CLOSED_AUCTION, ELIF, 99999, "k1")


def test_not_started_auction_rejects_bids(db):
    with pytest.raises(AuctionNotActive, match="başlamadı"):
        BidService(db).place_bid(SCHEDULED_AUCTION, ELIF, 30000, "k1")


def test_bid_after_end_time_rejected_by_server_clock(db):
    set_end_in(-1)  # durum hâlâ ACTIVE ama sunucu saatine göre süre doldu
    with pytest.raises(AuctionNotActive, match="süresi doldu"):
        BidService(db).place_bid(LIVE_AUCTION, ELIF, 11750, "k1")
    assert bid_count() == 4


# ------------------------------------------------------------ anti-sniping
def test_bid_in_last_two_minutes_extends_auction(db):
    disable_auto_bids()
    set_end_in(60)
    before = auction_row()

    outcome = BidService(db).place_bid(LIVE_AUCTION, ELIF, 11750, "k1")

    after = auction_row()
    assert outcome.extended is True
    assert after.end_time - before.end_time == timedelta(seconds=120)
    assert after.extension_count == before.extension_count + 1
    logs = run_sql(
        "SELECT count(*) FROM audit_logs WHERE action = 'AUCTION_EXTENDED' "
        "AND entity_id = :a AND created_at > now() - interval '1 minute'",
        a=LIVE_AUCTION,
    ).scalar_one()
    assert logs == 1


def test_bid_outside_window_does_not_extend(db):
    disable_auto_bids()
    set_end_in(600)
    before = auction_row()
    outcome = BidService(db).place_bid(LIVE_AUCTION, ELIF, 11750, "k1")
    assert outcome.extended is False
    assert auction_row().end_time == before.end_time


def test_rejected_bid_in_window_does_not_extend(db):
    set_end_in(60)
    before = auction_row()
    with pytest.raises(BidTooLow):
        BidService(db).place_bid(LIVE_AUCTION, ELIF, 11600, "k1")
    assert auction_row().end_time == before.end_time


# ------------------------------------------------------------ mükerrer istek
def test_retry_with_same_key_does_not_create_second_bid(db):
    disable_auto_bids()
    first = BidService(db).place_bid(LIVE_AUCTION, ELIF, 11750, "retry-1")
    second = BidService(db).place_bid(LIVE_AUCTION, ELIF, 11750, "retry-1")

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.current_price == 11750
    assert bid_count() == 5


def test_same_key_for_different_amount_is_conflict(db):
    disable_auto_bids()
    BidService(db).place_bid(LIVE_AUCTION, ELIF, 11750, "retry-1")
    with pytest.raises(IdempotencyConflict):
        BidService(db).place_bid(LIVE_AUCTION, ELIF, 12500, "retry-1")


# ------------------------------------------------------------ otomatik teklif
def test_auto_bid_counters_manual_bid(db):
    # Can'in 13.000 TL limiti var; Mehmet 11.750 verince sistem Can adına 12.000 verir.
    outcome = BidService(db).place_bid(LIVE_AUCTION, MEHMET, 11750, "k1")

    assert [(b.bidder_id, b.amount, b.is_auto) for b in outcome.bids] == [
        (MEHMET, 11750, False),
        (CAN_AUTO, 12000, True),
    ]
    assert outcome.highest_bidder_id == CAN_AUTO
    assert outcome.current_price == 12000


def test_auto_bid_never_exceeds_limit(db):
    outcome = BidService(db).place_bid(LIVE_AUCTION, MEHMET, 13000, "k1")
    assert outcome.highest_bidder_id == MEHMET
    assert outcome.current_price == 13000
    assert len(outcome.bids) == 1


def test_auto_bid_matches_limit_when_increment_would_exceed_it(db):
    # 12.900 + 250 > 13.000, Can limitine (13.000) kadar çıkar ve önde kalır.
    outcome = BidService(db).place_bid(LIVE_AUCTION, MEHMET, 12750, "k1")
    assert outcome.highest_bidder_id == CAN_AUTO
    assert outcome.current_price == 13000


def test_two_auto_bidders_settle_at_second_limit_plus_increment(db):
    # Elif 12.500 limit koyar, Can'in limiti 13.000: Can 12.750 ile kazanır.
    outcome = BidService(db).set_auto_bid_limit(LIVE_AUCTION, ELIF, 12500)

    assert outcome.highest_bidder_id == CAN_AUTO
    assert outcome.current_price == 12750
    assert [(b.bidder_id, b.amount) for b in outcome.bids] == [(ELIF, 12500), (CAN_AUTO, 12750)]


def test_auto_bid_limit_below_minimum_rejected(db):
    with pytest.raises(BidTooLow):
        BidService(db).set_auto_bid_limit(LIVE_AUCTION, ELIF, 11600)
