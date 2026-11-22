"""
Modellerin (app/models.py) veritabanıyla uyumunu kontrol eder.

Çalıştırma (backend klasöründe, sanal ortam aktifken):
    python check_db.py

Önce docs/schema.sql ve docs/seed.sql yüklenmiş olmalı.
Veritabanında hiçbir şeyi kalıcı olarak değiştirmez.
"""
import sys

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import configure_mappers

from app.core.database import Base, SessionLocal, engine
from app.models import Appointment, Auction, Bid, Dispute

hatalar = []


def kontrol(kosul, mesaj):
    print(("  ✓ " if kosul else "  ✗ ") + mesaj)
    if not kosul:
        hatalar.append(mesaj)


def main():
    print("1) Modeller yükleniyor")
    configure_mappers()
    kontrol(True, f"{len(Base.metadata.tables)} model tanımlı")

    print("2) Veritabanı bağlantısı")
    try:
        with engine.connect():
            pass
    except Exception as e:
        print(f"  ✗ Bağlanılamadı: {e}")
        print("    Postgres.app açık mı? 'bidarena' veritabanı var mı?")
        sys.exit(1)
    kontrol(True, f"Bağlandı: {engine.url.render_as_string(hide_password=True)}")

    print("3) Tablolar ve sütunlar schema.sql ile aynı mı")
    insp = inspect(engine)
    db_tablolari = set(insp.get_table_names())
    model_tablolari = set(Base.metadata.tables)
    for t in sorted(db_tablolari - model_tablolari):
        kontrol(False, f"'{t}' tablosu veritabanında var ama modeli yok")
    for t in sorted(model_tablolari - db_tablolari):
        kontrol(False, f"'{t}' modeli var ama veritabanında tablo yok")
    for t in sorted(model_tablolari & db_tablolari):
        model_sut = {c.name for c in Base.metadata.tables[t].columns}
        db_sut = {c["name"] for c in insp.get_columns(t)}
        eksik, fazla = db_sut - model_sut, model_sut - db_sut
        if eksik or fazla:
            kontrol(False, f"{t}: modelde eksik {sorted(eksik)}, modelde fazla {sorted(fazla)}")
    if not any("tablo" in h or "modelde" in h for h in hatalar):
        kontrol(True, f"{len(model_tablolari)} tablonun tüm sütunları eşleşiyor")

    print("4) Örnek veri (seed.sql) okunabiliyor mu")
    beklenen = {"users": 9, "listings": 6, "auctions": 5, "bids": 11,
                "appointments": 3, "backup_offers": 2, "disputes": 2}
    with SessionLocal() as db:
        for t, n in beklenen.items():
            sayi = db.scalar(select(func.count()).select_from(Base.metadata.tables[t]))
            kontrol(sayi == n, f"{t}: {sayi} kayıt (beklenen {n})")

        a = db.get(Auction, 1)
        kontrol(a is not None and a.status == "ACTIVE", "Senaryo 1: bisiklet açık artırması aktif")
        if a is not None:
            kontrol(a.highest_bid is not None and a.highest_bid.amount == 11500,
                    f"'{a.listing.title}' en yüksek teklif: {a.highest_bid.amount if a.highest_bid else '-'} TL")
            kontrol(len(a.bids) == 4, f"Bisiklete {len(a.bids)} teklif verilmiş")

        en_yuksek = db.scalars(select(Bid).where(Bid.auction_id == 1)
                               .order_by(Bid.amount.desc())).first()
        kontrol(en_yuksek is not None and en_yuksek.bidder.full_name == "Can Arslan",
                "En yüksek teklif sorgusu çalışıyor (Can Arslan, otomatik teklif)")

        r = db.get(Appointment, 2)
        kontrol(r is not None and r.status == "COMPLETED" and len(r.confirmations) == 2,
                "Senaryo 2: MacBook teslimi çift onaylı ve tamamlanmış")

        d = db.get(Dispute, 2)
        kontrol(d is not None and d.status == "OPEN" and len(d.evidence) == 2,
                "Senaryo 4: uyuşmazlıkta 2 kanıt var")

    print("5) Yazma ve kilitleme (işlem sonunda geri alınır)")
    with SessionLocal() as db:
        try:
            a = db.execute(select(Auction).where(Auction.id == 1).with_for_update()).scalar_one()
            kontrol(True, "SELECT ... FOR UPDATE ile satır kilitlendi (ADR-02)")
            yeni = Bid(auction_id=a.id, bidder_id=5, amount=a.current_price + a.min_increment,
                       idempotency_key="check-db-test")
            db.add(yeni)
            db.flush()
            kontrol(yeni.id is not None and yeni.created_at is not None and yeni.is_auto is False,
                    f"Yeni teklif eklenebiliyor (id={yeni.id}, {yeni.amount} TL)")
        finally:
            db.rollback()

    print()
    if hatalar:
        print(f"SONUÇ: {len(hatalar)} sorun bulundu.")
        sys.exit(1)
    print("SONUÇ: Her şey yolunda. Modeller veritabanıyla uyumlu.")


if __name__ == "__main__":
    main()
