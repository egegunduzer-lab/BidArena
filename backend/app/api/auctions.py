"""Açık artırma listeleme uç noktası."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.schemas import AuctionSummary
from app.services.auction_queries import AuctionQueries

router = APIRouter(tags=["Açık artırma ve teklifler"])


@router.get("/auctions", response_model=list[AuctionSummary])
async def list_auctions(db: Session = Depends(get_db)):
    """Tüm açık artırmalar: önce canlı olanlar, sonra başlayacaklar, en son kapananlar."""
    return await run_in_threadpool(AuctionQueries(db).list_auctions)
