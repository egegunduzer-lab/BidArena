"""API istek/yanıt şemaları (Pydantic). Girdi doğrulaması burada yapılır."""
from pydantic import BaseModel, Field


class BidRequest(BaseModel):
    amount: int = Field(gt=0, description="Teklif tutarı (TL, tam sayı)")


class AutoBidRequest(BaseModel):
    max_amount: int = Field(gt=0, description="Otomatik teklif üst limiti (TL)")


class PlacedBidOut(BaseModel):
    id: int
    bidder_id: int
    amount: int
    is_auto: bool
    created_at: str


class BidResponse(BaseModel):
    auction_id: int
    current_price: int
    min_next_bid: int
    highest_bidder_id: int | None
    end_time: str
    server_time: str
    extended: bool
    duplicate: bool
    bids: list[PlacedBidOut]


class ListingInfo(BaseModel):
    id: int
    title: str
    description: str | None
    defects: str | None
    category: str | None
    city: str | None
    district: str | None
    seller_id: int


class AuctionState(BaseModel):
    auction_id: int
    status: str
    start_price: int
    min_increment: int
    current_price: int
    min_next_bid: int
    highest_bidder_id: int | None
    winner_id: int | None
    end_time: str
    server_time: str
    listing: ListingInfo
    bids: list[PlacedBidOut]


class AuctionSummary(BaseModel):
    auction_id: int
    title: str
    status: str
    current_price: int
    end_time: str
    bid_count: int


class ErrorResponse(BaseModel):
    code: str
    message: str
    min_amount: int | None = None
