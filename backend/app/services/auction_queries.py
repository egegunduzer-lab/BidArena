"""Açık artırma listeleme sorguları (yalnızca okuma, kilit almaz)."""
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Auction, Bid, Listing

# Listede önce canlı, sonra başlayacak, en son kapanmış açık artırmalar gelir.
STATUS_ORDER = case(
    (Auction.status == "ACTIVE", 0), (Auction.status == "SCHEDULED", 1), else_=2
)


class AuctionQueries:
    def __init__(self, db: Session):
        self.db = db

    def list_auctions(self) -> list[dict]:
        bid_count = (
            select(func.count(Bid.id)).where(Bid.auction_id == Auction.id).scalar_subquery()
        )
        rows = self.db.execute(
            select(Auction, Listing.title, bid_count)
            .join(Listing, Listing.id == Auction.listing_id)
            .order_by(STATUS_ORDER, Auction.end_time)
        ).all()
        return [
            {
                "auction_id": auction.id,
                "title": title,
                "status": auction.status,
                "current_price": auction.current_price,
                "end_time": auction.end_time.isoformat(),
                "bid_count": count,
            }
            for auction, title, count in rows
        ]
