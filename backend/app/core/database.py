"""
Veritabanı bağlantısı (SQLAlchemy).

Bağlantı adresi DATABASE_URL ortam değişkeninden okunur. Tanımlı değilse
yerel PostgreSQL'deki `bidarena` veritabanı kullanılır (Postgres.app'te
kullanıcı adı/şifre gerekmez).

Farklı bir bağlantı için örnek:
    export DATABASE_URL="postgresql+psycopg2://kullanici:sifre@localhost:5432/bidarena"

Not: Tabloları bu kod OLUŞTURMAZ. Tek kaynak docs/schema.sql'dir:
    psql -d bidarena -f docs/schema.sql
    psql -d bidarena -f docs/seed.sql
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://localhost:5432/bidarena"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Tüm modellerin türediği temel sınıf (app/models.py)."""


def get_db():
    """FastAPI bağımlılığı: her istek için bir oturum açar, iş bitince kapatır.

    Kullanım:
        from fastapi import Depends
        from sqlalchemy.orm import Session
        from app.core.database import get_db
        from app.models import Auction

        @router.get("/auctions/{auction_id}")
        def get_auction(auction_id: int, db: Session = Depends(get_db)):
            return db.get(Auction, auction_id)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
