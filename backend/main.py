import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auctions, bids, realtime
from app.core.scheduler import auction_closer_loop, closer_enabled, closer_interval
from app.core.websocket_manager import manager
from app.services.auction_service import AuctionCloser


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if closer_enabled():
        task = asyncio.create_task(
            auction_closer_loop(AuctionCloser(), manager, closer_interval())
        )
    yield
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="BidArena API",
    description="Gerçek Zamanlı Mobil Açık Artırma Platformu API Servisleri",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auctions.router, prefix="/api")
app.include_router(bids.router, prefix="/api")
app.include_router(realtime.router)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": "BidArena Engine",
        "message": "Backend servisi başarıyla çalışıyor."
    }
