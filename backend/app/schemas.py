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


class ListingCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    defects: str | None = Field(default=None, max_length=2000, description="Ürün kusurları")
    category: str | None = Field(default=None, max_length=60)
    city: str | None = Field(default=None, max_length=60)
    district: str | None = Field(default=None, max_length=60)
    photos: list[str] | None = Field(default=None, max_length=10, description="Fotoğraf adresleri")
    safe_meeting_prefs: dict | None = Field(default=None, description="Güvenli buluşma tercihleri")
    start_price: int = Field(gt=0, description="Başlangıç fiyatı (TL)")
    min_increment: int = Field(gt=0, description="Minimum teklif artışı (TL)")
    duration_minutes: int = Field(ge=1, le=43200, description="Açık artırma süresi (en fazla 30 gün)")


class QuotaOut(BaseModel):
    subscription_id: int
    plan: str
    quota: int
    used: int
    remaining: int
    ends_at: str


class ListingCreated(BaseModel):
    listing_id: int
    auction_id: int
    end_time: str
    quota: QuotaOut


class ErrorResponse(BaseModel):
    code: str
    message: str
    min_amount: int | None = None
