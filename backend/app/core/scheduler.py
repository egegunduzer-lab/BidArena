"""
Açık artırma kapanış zamanlayıcısı (ADR-03).

Uygulama açılınca arka planda çalışan tek bir asyncio görevi, belirli
aralıklarla AuctionCloser.run_once() çağırır ve sonuçları WebSocket
odalarına yayınlar:
    AUCTION_STARTED  başlama saati gelen açık artırma aktifleşti
    AUCTION_CLOSED   süre doldu, kazanan belirlendi (ya da teklif yok)

Ayarlar (ortam değişkeni):
    AUCTION_CLOSER_ENABLED   "0" ise zamanlayıcı çalışmaz (testlerde kapalı)
    AUCTION_CLOSER_INTERVAL  saniye cinsinden tur aralığı (varsayılan 1)
"""
import asyncio
import logging
import os

from starlette.concurrency import run_in_threadpool

from app.core.websocket_manager import ConnectionManager
from app.services.auction_service import AuctionCloser

log = logging.getLogger("bidarena.scheduler")


def closer_enabled() -> bool:
    return os.getenv("AUCTION_CLOSER_ENABLED", "1") != "0"


def closer_interval() -> float:
    return float(os.getenv("AUCTION_CLOSER_INTERVAL", "1"))


async def run_closer_tick(closer: AuctionCloser, manager: ConnectionManager) -> None:
    # Kapanış bloklayan veritabanı çağrıları yapar; event loop'u tıkamasın.
    run = await run_in_threadpool(closer.run_once)
    for auction_id in run.started:
        await manager.broadcast_to_auction(
            auction_id, {"event": "AUCTION_STARTED", "auction_id": auction_id}
        )
    for closed in run.closed:
        log.info("Açık artırma %s kapandı, kazanan: %s", closed.auction_id, closed.winner_id)
        await manager.broadcast_to_auction(closed.auction_id, closed.to_event())


async def auction_closer_loop(
    closer: AuctionCloser, manager: ConnectionManager, interval: float
) -> None:
    while True:
        try:
            await run_closer_tick(closer, manager)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Bir turdaki hata (ör. veritabanı geçici olarak yok) döngüyü
            # öldürmemeli; bir sonraki turda yeniden denenir.
            log.exception("Kapanış turu başarısız")
        await asyncio.sleep(interval)
