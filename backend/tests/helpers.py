"""Testlerde ortak kullanılan sabitler ve veritabanı yardımcıları."""
from pathlib import Path

from sqlalchemy import text

from app.core.database import engine

SEED_SQL = (Path(__file__).resolve().parents[2] / "docs" / "seed.sql").read_text(encoding="utf-8")

# Seed verisindeki kullanıcılar ve açık artırmalar (docs/seed.sql)
SELLER = 2            # Ahmet, açık artırma 1'in satıcısı
UNVERIFIED = 4        # Deniz, doğrulanmamış yeni hesap
MEHMET = 5
ELIF = 6
CAN_AUTO = 7          # Can, açık artırma 1'de en yüksek teklif sahibi, 13.000 TL otomatik limiti var
RESTRICTED = 9        # geçici kısıtlı kullanıcı
LIVE_AUCTION = 1      # Senaryo 1: bisiklet, güncel fiyat 11.500, artış 250
CLOSED_AUCTION = 2
SCHEDULED_AUCTION = 4  # başlangıç 30.000, artış 500, henüz başlamadı


def run_sql(sql: str, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


def disable_auto_bids(auction_id: int = LIVE_AUCTION):
    run_sql("UPDATE auto_bid_limits SET is_active = false WHERE auction_id = :a", a=auction_id)


def set_end_in(seconds: float, auction_id: int = LIVE_AUCTION):
    run_sql(
        "UPDATE auctions SET end_time = clock_timestamp() + make_interval(secs => :s) WHERE id = :a",
        s=seconds,
        a=auction_id,
    )


def create_bidders(count: int, first_id: int = 1001) -> list[int]:
    """Eşzamanlılık testleri için doğrulanmış kullanıcılar ekler."""
    ids = list(range(first_id, first_id + count))
    run_sql(
        """
        INSERT INTO users (id, email, password_hash, full_name, is_verified)
        SELECT i, 'bidder' || i || '@test.local', 'TEST', 'Test Teklifçi ' || i, true
        FROM unnest(CAST(:ids AS int[])) AS i
        """,
        ids=ids,
    )
    return ids


def auction_row(auction_id: int = LIVE_AUCTION):
    return run_sql(
        "SELECT current_price, highest_bid_id, end_time, extension_count, status "
        "FROM auctions WHERE id = :a",
        a=auction_id,
    ).one()


def bid_count(auction_id: int = LIVE_AUCTION) -> int:
    return run_sql("SELECT count(*) FROM bids WHERE auction_id = :a", a=auction_id).scalar_one()
