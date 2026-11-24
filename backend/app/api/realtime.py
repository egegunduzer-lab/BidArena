"""
Canlı açık artırma WebSocket kanalı.

İstemci `/ws/auctions/{auction_id}` adresine bağlanır. Bağlanınca anlık durumu
(SNAPSHOT: fiyat, bitiş zamanı, sunucu saati, son teklifler) alır; sonra her
kabul edilen teklifte NEW_BID mesajı gelir. Teklif verme REST üzerinden
yapılır (POST /api/auctions/{id}/bids); WebSocket yalnızca yayın içindir.
Böylece teklif doğrulama, idempotency ve hata kodları tek yerde kalır.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.concurrency import run_in_threadpool

from app.core.database import SessionLocal
from app.core.websocket_manager import manager
from app.services.bid_service import BidService
from app.services.errors import AuctionNotFound

router = APIRouter()


def _snapshot(auction_id: int) -> dict:
    with SessionLocal() as db:
        return BidService(db).get_state(auction_id)


@router.websocket("/ws/auctions/{auction_id}")
async def auction_feed(websocket: WebSocket, auction_id: int):
    try:
        snapshot = await run_in_threadpool(_snapshot, auction_id)
    except AuctionNotFound:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(auction_id, websocket)
    try:
        await websocket.send_json(snapshot)
        while True:
            # İstemciden gelen mesajlar (ör. "ping") yalnızca bağlantıyı canlı tutar.
            if await websocket.receive_text() == "ping":
                await websocket.send_json({"event": "PONG"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(auction_id, websocket)
