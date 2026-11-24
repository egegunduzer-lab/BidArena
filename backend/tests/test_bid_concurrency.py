"""
Eşzamanlılık testleri (doküman bölüm 8, ADR-02).

Her teklif ayrı thread ve ayrı veritabanı bağlantısıyla gönderilir; bir
Barrier hepsini aynı anda serbest bırakır. Pessimistic locking doğru
çalışıyorsa sonuç her çalıştırmada tutarlı olmalıdır.
"""
import random
import threading
from concurrent.futures import ThreadPoolExecutor

from app.core.database import SessionLocal
from app.services.bid_service import BidService
from app.services.errors import BidError, BidTooLow
from helpers import (
    ELIF,
    LIVE_AUCTION,
    auction_row,
    bid_count,
    create_bidders,
    disable_auto_bids,
    run_sql,
)

N = 100


def fire_concurrently(requests):
    """requests: (bidder_id, amount, key) listesi. Hepsini aynı anda gönderir."""
    barrier = threading.Barrier(len(requests))

    def send(req):
        bidder_id, amount, key = req
        barrier.wait()
        with SessionLocal() as db:
            try:
                return BidService(db).place_bid(LIVE_AUCTION, bidder_id, amount, key)
            except BidError as err:
                return err

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return list(pool.map(send, requests))


def accepted_bids():
    return run_sql(
        "SELECT id, bidder_id, amount FROM bids WHERE auction_id = :a AND id > 11 ORDER BY id",
        a=LIVE_AUCTION,
    ).all()


def test_100_concurrent_bids_with_different_amounts_stay_consistent():
    disable_auto_bids()
    bidders = create_bidders(N)
    amounts = [11750 + i * 250 for i in range(N)]
    random.shuffle(amounts)

    results = fire_concurrently(
        [(u, a, f"conc-{u}") for u, a in zip(bidders, amounts)]
    )

    errors = [r for r in results if isinstance(r, Exception)]
    assert all(isinstance(e, BidTooLow) for e in errors), errors
    rows = accepted_bids()
    assert len(rows) == N - len(errors)
    assert bid_count() == 4 + len(rows)

    # Kabul edilen teklifler işlenme sırasına göre kesin artan olmalı:
    # hiçbir teklif, kendinden önce kabul edilen tekliften düşük olamaz.
    accepted = [r.amount for r in rows]
    assert accepted == sorted(accepted) and len(set(accepted)) == len(accepted)
    assert all(b - a >= 250 for a, b in zip(accepted, accepted[1:]))

    # Açık artırmanın güncel fiyatı ve en yüksek teklifi son kabul edilen teklif.
    row = auction_row()
    assert row.current_price == accepted[-1]
    assert row.highest_bid_id == rows[-1].id
    # En yüksek tutar (36.500) her durumda kabul edilmiş olmalı.
    assert row.current_price == max(amounts)


def test_100_concurrent_bids_with_same_amount_accept_exactly_one():
    disable_auto_bids()
    bidders = create_bidders(N)

    results = fire_concurrently([(u, 11750, f"same-{u}") for u in bidders])

    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, Exception)]
    assert len(winners) == 1
    assert len(losers) == N - 1
    assert all(isinstance(e, BidTooLow) and e.min_amount == 12000 for e in losers)
    assert bid_count() == 5
    row = auction_row()
    assert row.current_price == 11750
    assert winners[0].highest_bidder_id in bidders


def test_duplicate_requests_sent_concurrently_create_one_bid():
    disable_auto_bids()
    results = fire_concurrently([(ELIF, 11750, "double-click")] * 30)

    assert not any(isinstance(r, Exception) for r in results)
    assert sum(1 for r in results if not r.duplicate) == 1
    assert all(r.current_price == 11750 for r in results)
    assert bid_count() == 5


def test_concurrent_bids_against_auto_bidder_respect_limit():
    # Can'in 13.000 TL otomatik limiti açıkken 100 kişi aynı anda teklif verir.
    bidders = create_bidders(N)
    amounts = [11750 + i * 50 for i in range(N)]  # 11.750 .. 16.700
    results = fire_concurrently([(u, a, f"auto-{u}") for u, a in zip(bidders, amounts)])

    assert all(isinstance(r, BidTooLow) for r in results if isinstance(r, Exception))
    auto_amounts = [
        a for (a,) in run_sql(
            "SELECT amount FROM bids WHERE auction_id = :a AND is_auto AND id > 11", a=LIVE_AUCTION
        ).all()
    ]
    assert all(a <= 13000 for a in auto_amounts)
    row = auction_row()
    assert row.current_price == max(amounts)
