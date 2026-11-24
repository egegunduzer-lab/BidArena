"""
Test altyapısı.

Testler gerçek PostgreSQL'e karşı çalışır (satır kilitleri ve unique index'ler
SQLite ile test edilemez). Her testten önce docs/seed.sql yeniden yüklenir,
yani veritabanı her test için örnek veriyle sıfırlanır.

DİKKAT: seed.sql tabloları boşaltır. Testleri ayrı bir test veritabanında
çalıştırın:
    createdb bidarena_test
    psql -d bidarena_test -f ../docs/schema.sql
    TEST_DATABASE_URL=postgresql+psycopg2://localhost:5432/bidarena_test pytest
"""
import os

if os.getenv("TEST_DATABASE_URL"):
    # app.core.database import edilmeden önce ayarlanmalı.
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

import pytest

from app.core.database import SessionLocal, engine
from helpers import SEED_SQL


@pytest.fixture(scope="session", autouse=True)
def _database_available():
    try:
        with engine.connect():
            pass
    except Exception as e:  # pragma: no cover
        pytest.exit(f"Test veritabanına bağlanılamadı: {e}", returncode=1)


@pytest.fixture(autouse=True)
def reset_db():
    raw = engine.raw_connection()
    try:
        raw.autocommit = True
        with raw.cursor() as cur:
            cur.execute(SEED_SQL)
    finally:
        raw.close()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
