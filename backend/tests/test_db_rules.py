"""
Veritabanı seviyesindeki iş kuralları (doküman bölüm 8, docs/schema.sql).

- Teslimat çift onay olmadan tamamlanamaz: appointments_double_confirmation trigger'ı
- Her taraf (alıcı / satıcı) bir randevuyu yalnızca bir kez onaylar: unique index
- Bir açık artırmada aynı anda yalnızca bir aktif (PENDING) yedek davet olabilir:
  kısmi unique index

Bu kurallar uygulama kodundan bağımsız olarak veritabanında korunur; servis
katmanında bir hata olsa bile ihlal eden kayıt veritabanına giremez.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import engine
from helpers import CAN_AUTO, CLOSED_AUCTION, ELIF, LIVE_AUCTION, MEHMET, SELLER, run_sql

DOUBLE_CONFIRMATION = "alici ve satici onayi gerekli"


# ------------------------------------------------------------ yardımcılar
def new_appointment(status="MATCHED"):
    """Açık artırma 1 için yeni bir randevu açar (alıcı Can, satıcı Ahmet)."""
    return run_sql(
        "INSERT INTO appointments (auction_id, buyer_id, seller_id, agreed_price, status) "
        "VALUES (:a, :b, :s, 11500, :st) RETURNING id",
        a=LIVE_AUCTION, b=CAN_AUTO, s=SELLER, st=status,
    ).scalar_one()


def confirm(appointment_id, user_id, party):
    run_sql(
        "INSERT INTO delivery_confirmations (appointment_id, user_id, party) VALUES (:a, :u, :p)",
        a=appointment_id, u=user_id, p=party,
    )


def complete(appointment_id):
    run_sql("UPDATE appointments SET status = 'COMPLETED' WHERE id = :a", a=appointment_id)


def status_of(appointment_id):
    return run_sql("SELECT status FROM appointments WHERE id = :a", a=appointment_id).scalar_one()


def invite(user_id, bid_id, rank, auction_id=CLOSED_AUCTION, status="PENDING"):
    run_sql(
        "INSERT INTO backup_offers (auction_id, user_id, bid_id, price, rank, status, expires_at) "
        "SELECT :a, :u, id, amount, :r, :st, now() + interval '1 day' FROM bids WHERE id = :bid",
        a=auction_id, u=user_id, bid=bid_id, r=rank, st=status,
    )


def pending_count(auction_id=CLOSED_AUCTION):
    return run_sql(
        "SELECT count(*) FROM backup_offers WHERE auction_id = :a AND status = 'PENDING'",
        a=auction_id,
    ).scalar_one()


# ------------------------------------------------------------ çift onay
def test_delivery_cannot_complete_without_any_confirmation():
    appointment = new_appointment()
    with pytest.raises(DBAPIError, match=DOUBLE_CONFIRMATION):
        complete(appointment)
    assert status_of(appointment) == "MATCHED"


def test_delivery_cannot_complete_with_buyer_confirmation_only():
    appointment = new_appointment()
    confirm(appointment, CAN_AUTO, "BUYER")
    with pytest.raises(DBAPIError, match=DOUBLE_CONFIRMATION):
        complete(appointment)
    assert status_of(appointment) == "MATCHED"


def test_delivery_cannot_complete_with_seller_confirmation_only():
    appointment = new_appointment()
    confirm(appointment, SELLER, "SELLER")
    with pytest.raises(DBAPIError, match=DOUBLE_CONFIRMATION):
        complete(appointment)


def test_delivery_completes_when_both_parties_confirm():
    appointment = new_appointment()
    confirm(appointment, CAN_AUTO, "BUYER")
    confirm(appointment, SELLER, "SELLER")
    complete(appointment)
    assert status_of(appointment) == "COMPLETED"


def test_appointment_cannot_be_inserted_as_completed():
    # Trigger INSERT'te de çalışır: kayıt doğrudan COMPLETED olarak açılamaz.
    with pytest.raises(DBAPIError, match=DOUBLE_CONFIRMATION):
        new_appointment(status="COMPLETED")


def test_same_party_cannot_confirm_twice():
    # Aynı tarafın iki onayı "iki onay" sayılmamalı.
    appointment = new_appointment()
    confirm(appointment, CAN_AUTO, "BUYER")
    with pytest.raises(IntegrityError):
        confirm(appointment, ELIF, "BUYER")
    with pytest.raises(DBAPIError, match=DOUBLE_CONFIRMATION):
        complete(appointment)


def test_same_user_cannot_confirm_twice():
    appointment = new_appointment()
    confirm(appointment, CAN_AUTO, "BUYER")
    with pytest.raises(IntegrityError):
        confirm(appointment, CAN_AUTO, "SELLER")


# ------------------------------------------------------------ tek aktif yedek davet
# Seed: açık artırma 2'de rank 1 (Can) REJECTED, rank 2 (Elif) PENDING.
# Açık artırma 2'deki teklifler: 5 (Elif 5.100), 6 (Can 5.300), 7 (Mehmet 5.600).

def test_second_pending_backup_offer_is_rejected():
    assert pending_count() == 1
    with pytest.raises(IntegrityError):
        invite(MEHMET, bid_id=7, rank=3)
    assert pending_count() == 1


def test_next_candidate_can_be_invited_after_previous_expires():
    run_sql("UPDATE backup_offers SET status = 'EXPIRED' WHERE auction_id = :a AND status = 'PENDING'",
            a=CLOSED_AUCTION)
    invite(MEHMET, bid_id=7, rank=3)
    assert pending_count() == 1


def test_non_pending_offers_do_not_block_each_other():
    # Kısıt yalnızca PENDING davetler için: geçmişteki ret / süre aşımları birikebilir.
    run_sql("UPDATE backup_offers SET status = 'REJECTED' WHERE auction_id = :a", a=CLOSED_AUCTION)
    invite(MEHMET, bid_id=7, rank=3, status="EXPIRED")
    assert pending_count() == 0


def test_same_rank_cannot_be_used_twice():
    run_sql("UPDATE backup_offers SET status = 'EXPIRED' WHERE auction_id = :a", a=CLOSED_AUCTION)
    with pytest.raises(IntegrityError):
        invite(MEHMET, bid_id=7, rank=2)  # rank 2 Elif'te


def test_concurrent_invitations_create_only_one_pending_offer():
    """İki satıcı isteği aynı anda farklı adaylara davet gönderse de tek davet aktif olur."""
    run_sql("UPDATE backup_offers SET status = 'EXPIRED' WHERE auction_id = :a AND status = 'PENDING'",
            a=CLOSED_AUCTION)
    barrier = threading.Barrier(2)

    def send(user_id, bid_id, rank):
        barrier.wait()
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO backup_offers (auction_id, user_id, bid_id, price, rank, expires_at) "
                         "SELECT :a, :u, id, amount, :r, now() + interval '1 day' FROM bids WHERE id = :bid"),
                    {"a": CLOSED_AUCTION, "u": user_id, "bid": bid_id, "r": rank},
                )
            return "ok"
        except IntegrityError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: send(*args), [(MEHMET, 7, 3), (SELLER, 5, 4)]))

    assert sorted(results) == ["ok", "rejected"]
    assert pending_count() == 1
