"""İlan açma ve ilan kotasının sunucu tarafında kontrolü (doküman bölüm 8, Issue #7)."""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.services.errors import ListingQuotaExceeded, NoActiveSubscription, UserNotFound
from app.services.listing_service import ListingDraft, ListingService
from helpers import ELIF, MEHMET, SELLER, run_sql
from main import app

PRO_SELLER = 3          # Tekno Mağaza: profesyonel plan (200), 2 ilan kullanılmış
INDIVIDUAL_SUB = 1      # Ahmet'in bireysel planı (20), 4 ilan kullanılmış

DRAFT = ListingDraft(
    title="Sony WH-1000XM5 Kulaklık",
    description="Kutulu, faturalı.",
    defects="Kafa bandında hafif aşınma.",
    category="Elektronik",
    city="İstanbul",
    district="Beşiktaş",
    start_price=4000,
    min_increment=100,
    duration_minutes=60,
)


def listing_count(subscription_id=INDIVIDUAL_SUB):
    return run_sql(
        "SELECT count(*) FROM listings WHERE subscription_id = :s", s=subscription_id
    ).scalar_one()


def set_quota(quota, subscription_id=INDIVIDUAL_SUB):
    run_sql("UPDATE subscriptions SET listing_quota = :q WHERE id = :s", q=quota, s=subscription_id)


# ------------------------------------------------------------ ilan açma
def test_seller_creates_listing_with_live_auction(db):
    created = ListingService(db).create_listing(SELLER, DRAFT)

    listing = run_sql(
        "SELECT seller_id, subscription_id, title, defects, status FROM listings WHERE id = :i",
        i=created.listing_id,
    ).one()
    assert (listing.seller_id, listing.subscription_id, listing.status) == (SELLER, INDIVIDUAL_SUB, "ACTIVE")
    assert listing.defects == "Kafa bandında hafif aşınma."

    auction = run_sql(
        "SELECT listing_id, start_price, current_price, min_increment, status, "
        "end_time - start_time AS duration FROM auctions WHERE id = :i",
        i=created.auction_id,
    ).one()
    assert auction.listing_id == created.listing_id
    assert (auction.start_price, auction.current_price, auction.min_increment) == (4000, 4000, 100)
    assert auction.status == "ACTIVE"
    assert auction.duration == timedelta(minutes=60)


def test_created_listing_uses_one_quota_slot(db):
    created = ListingService(db).create_listing(SELLER, DRAFT)
    assert (created.quota.quota, created.quota.used, created.quota.remaining) == (20, 5, 15)
    assert listing_count() == 5


def test_quota_status(db):
    status = ListingService(db).quota_status(SELLER)
    assert (status.plan, status.quota, status.used, status.remaining) == ("INDIVIDUAL", 20, 4, 16)


def test_professional_plan_has_higher_quota(db):
    status = ListingService(db).quota_status(PRO_SELLER)
    assert (status.plan, status.quota, status.remaining) == ("PROFESSIONAL", 200, 198)


# ------------------------------------------------------------ kota ve üyelik kuralları
def test_listing_rejected_when_quota_is_full(db):
    set_quota(4)  # 4 ilan zaten açık
    with pytest.raises(ListingQuotaExceeded) as err:
        ListingService(db).create_listing(SELLER, DRAFT)
    assert err.value.quota == 4
    assert listing_count() == 4


def test_last_quota_slot_can_be_used(db):
    set_quota(5)
    created = ListingService(db).create_listing(SELLER, DRAFT)
    assert created.quota.remaining == 0
    with pytest.raises(ListingQuotaExceeded):
        ListingService(db).create_listing(SELLER, DRAFT)


def test_cancelled_listings_still_count_against_quota(db):
    # İptal edip yeniden açmak kotayı sıfırlamamalı.
    set_quota(4)
    run_sql("UPDATE listings SET status = 'CANCELLED' WHERE subscription_id = :s", s=INDIVIDUAL_SUB)
    with pytest.raises(ListingQuotaExceeded):
        ListingService(db).create_listing(SELLER, DRAFT)


def test_buyer_without_subscription_cannot_create_listing(db):
    with pytest.raises(NoActiveSubscription):
        ListingService(db).create_listing(MEHMET, DRAFT)


def test_expired_subscription_cannot_create_listing(db):
    # Elif'in bireysel planının süresi dolmuş (seed: subscription 3, EXPIRED).
    with pytest.raises(NoActiveSubscription):
        ListingService(db).create_listing(ELIF, DRAFT)


def test_subscription_past_end_date_is_not_active_even_if_status_says_so(db):
    # Durum ACTIVE kalmış olsa bile bitiş tarihi geçmişse geçerli sayılmaz.
    run_sql("UPDATE subscriptions SET ends_at = now() - interval '1 second' WHERE id = :s",
            s=INDIVIDUAL_SUB)
    with pytest.raises(NoActiveSubscription):
        ListingService(db).create_listing(SELLER, DRAFT)


def test_unknown_user(db):
    with pytest.raises(UserNotFound):
        ListingService(db).create_listing(999, DRAFT)


# ------------------------------------------------------------ eşzamanlılık
def test_concurrent_requests_cannot_exceed_quota():
    """Kotanın son hakkı için 10 istek aynı anda gelir: yalnızca biri kabul edilir."""
    set_quota(5)  # 4 kullanılmış, 1 hak kaldı
    barrier = threading.Barrier(10)

    def create(_):
        barrier.wait()
        with SessionLocal() as db:
            try:
                ListingService(db).create_listing(SELLER, DRAFT)
                return "ok"
            except ListingQuotaExceeded:
                return "full"

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(create, range(10)))

    assert results.count("ok") == 1
    assert results.count("full") == 9
    assert listing_count() == 5


# ------------------------------------------------------------ API
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


BODY = {
    "title": "Sony WH-1000XM5 Kulaklık",
    "defects": "Kafa bandında hafif aşınma.",
    "city": "İstanbul",
    "start_price": 4000,
    "min_increment": 100,
    "duration_minutes": 60,
}


def test_api_create_listing(client):
    r = client.post("/api/listings", json=BODY, headers={"X-User-Id": str(SELLER)})
    assert r.status_code == 201
    body = r.json()
    assert body["quota"]["remaining"] == 15
    # Yeni açık artırma hemen canlı ve teklif alabilir.
    state = client.get(f"/api/auctions/{body['auction_id']}").json()
    assert state["status"] == "ACTIVE"
    assert state["min_next_bid"] == 4000
    assert state["listing"]["title"] == BODY["title"]


def test_api_quota_full_returns_403(client):
    set_quota(4)
    r = client.post("/api/listings", json=BODY, headers={"X-User-Id": str(SELLER)})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "LISTING_QUOTA_EXCEEDED"
    assert r.json()["detail"]["quota"] == 4


def test_api_buyer_without_subscription_returns_403(client):
    r = client.post("/api/listings", json=BODY, headers={"X-User-Id": str(MEHMET)})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "NO_ACTIVE_SUBSCRIPTION"


def test_api_invalid_listing_rejected(client):
    bad = {**BODY, "start_price": 0, "duration_minutes": 0}
    r = client.post("/api/listings", json=bad, headers={"X-User-Id": str(SELLER)})
    assert r.status_code == 422


def test_api_my_quota(client):
    r = client.get("/api/sellers/me/quota", headers={"X-User-Id": str(SELLER)})
    assert r.status_code == 200
    assert r.json()["remaining"] == 16
    assert client.get("/api/sellers/me/quota", headers={"X-User-Id": str(MEHMET)}).status_code == 403
