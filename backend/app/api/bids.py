from fastapi import APIRouter
from app.core.websocket_manager import manager

router = APIRouter()

@router.post("/auctions/{auction_id}/bid")
async def place_bid(auction_id: int, amount: float, user_id: int):
    """
    Kullanıcıdan teklif alır, veritabanına yazar
    ardından WebSocket Manager üzerinden tüm dinleyicilere yeni fiyatı yayınlar.
    """
    
    # 1. TODO: Yağız'ın yazdığı veritabanı modelleriyle teklif tutarı kontrol edilecek.
    # 2. TODO: Pessimistic Locking ile satır kilitlenecek.
    
    # 3. İşlem başarılıysa anlık yayın yap:
    await manager.broadcast_to_auction(auction_id, {
        "event": "NEW_BID",
        "auction_id": auction_id,
        "new_price": amount,
        "bidder_id": user_id
    })

    return {"status": "success", "message": "Teklif alındı ve yayınlandı"}