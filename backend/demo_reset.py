"""
Demo öncesi veritabanını örnek veriye sıfırlar.

docs/seed.sql yeniden yüklenir (tüm tablolar boşaltılıp örnek veri yazılır).
İsteğe bağlı olarak bisiklet açık artırmasının (#1) bitişi yakın bir zamana
çekilir; böylece sunumda son dakika uzatması ve kapanış canlı gösterilebilir.

Kullanım (backend klasöründe, sanal ortam aktifken):
    python demo_reset.py                 # sadece örnek veriyi yükle
    python demo_reset.py --ends-in 180   # açık artırma 1, 3 dakika sonra bitsin

DİKKAT: DATABASE_URL'deki veritabanının tüm verisi silinir.
"""
import argparse
from pathlib import Path

from sqlalchemy import text

from app.core.database import engine

SEED_SQL = Path(__file__).resolve().parents[1] / "docs" / "seed.sql"
DEMO_AUCTION = 1


def main():
    parser = argparse.ArgumentParser(description="BidArena demo verisini sıfırlar.")
    parser.add_argument(
        "--ends-in", type=int, metavar="SANIYE",
        help="açık artırma 1'in kaç saniye sonra biteceği (ör. 180)",
    )
    args = parser.parse_args()

    raw = engine.raw_connection()
    try:
        raw.autocommit = True
        with raw.cursor() as cur:
            cur.execute(SEED_SQL.read_text(encoding="utf-8"))
    finally:
        raw.close()
    print(f"Örnek veri yüklendi ({engine.url.render_as_string(hide_password=True)})")

    if args.ends_in is not None:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE auctions SET end_time = clock_timestamp() + make_interval(secs => :s) "
                     "WHERE id = :id"),
                {"s": args.ends_in, "id": DEMO_AUCTION},
            )
        print(f"Açık artırma {DEMO_AUCTION} {args.ends_in} saniye sonra bitecek.")


if __name__ == "__main__":
    main()
