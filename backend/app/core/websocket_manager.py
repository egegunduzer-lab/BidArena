from typing import Dict, List
from fastapi import WebSocket

class ConnectionManager:
    """
    Observer Pattern prensibine uygun olarak canlı açık artırma 
    odalarını ve dinleyicileri (subscribers) yöneten WebSocket sınıfı.
    """
    def __init__(self):
        # auction_id -> List[WebSocket]
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, auction_id: int, websocket: WebSocket):
        await websocket.accept()
        if auction_id not in self.active_connections:
            self.active_connections[auction_id] = []
        self.active_connections[auction_id].append(websocket)

    def disconnect(self, auction_id: int, websocket: WebSocket):
        if auction_id in self.active_connections:
            self.active_connections[auction_id].remove(websocket)
            if not self.active_connections[auction_id]:
                del self.active_connections[auction_id]

    async def broadcast_to_auction(self, auction_id: int, message: dict):
        """İlgili açık artırmadaki tüm aktif istemcilere anlık teklif güncellemesini yayınlar."""
        if auction_id in self.active_connections:
            for connection in self.active_connections[auction_id]:
                await connection.send_json(message)

manager = ConnectionManager()