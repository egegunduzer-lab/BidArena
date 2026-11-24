import asyncio
from typing import Dict, Set

from fastapi import WebSocket


class ConnectionManager:
    """
    Observer Pattern: her açık artırma bir "konu" (subject), ona bağlı
    WebSocket istemcileri "gözlemci" (observer). Teklif kabul edildiğinde
    API katmanı broadcast_to_auction çağırır; o odadaki herkes haberdar olur.
    """

    def __init__(self):
        # auction_id -> o odayı dinleyen bağlantılar
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, auction_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(auction_id, set()).add(websocket)

    def disconnect(self, auction_id: int, websocket: WebSocket):
        room = self.active_connections.get(auction_id)
        if room is None:
            return
        room.discard(websocket)
        if not room:
            del self.active_connections[auction_id]

    def listener_count(self, auction_id: int) -> int:
        return len(self.active_connections.get(auction_id, ()))

    async def broadcast_to_auction(self, auction_id: int, message: dict):
        """Odadaki tüm istemcilere mesajı eşzamanlı gönderir.

        Kopmuş bir bağlantı diğerlerini engellemez: gönderim hatası veren
        bağlantı odadan çıkarılır, kalanlar mesajı almaya devam eder.
        """
        room = list(self.active_connections.get(auction_id, ()))
        if not room:
            return
        results = await asyncio.gather(
            *(ws.send_json(message) for ws in room), return_exceptions=True
        )
        for ws, result in zip(room, results):
            if isinstance(result, Exception):
                self.disconnect(auction_id, ws)


manager = ConnectionManager()
