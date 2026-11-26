"""
Teklif uç noktaları (REST).

Bu katman yalnızca HTTP ile ilgilenir: girdiyi doğrular, servisi çağırır,
iş kuralı hatalarını HTTP kodlarına çevirir ve işlem commit edildikten
SONRA yeni durumu WebSocket ile yayınlar. Kural mantığı BidService'tedir.

Kimlik doğrulama modülü henüz yok; teklif veren kullanıcı geçici olarak
`X-User-Id` başlığıyla belirtilir. Auth eklendiğinde yalnızca
`current_user_id` bağımlılığı değişecek, servis kodu değişmeyecek.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import current_user_id
from app.core.database import get_db
from app.core.websocket_manager import manager
from app.schemas import AuctionState, AutoBidRequest, BidRequest, BidResponse, ErrorResponse
from app.services.bid_service import BidOutcome, BidService
from app.services.errors import (
    AuctionNotActive,
    AuctionNotFound,
    BidError,
    BidNotAllowed,
    BidTooLow,
    IdempotencyConflict,
    UserNotFound,
)

router = APIRouter(tags=["Açık artırma ve teklifler"])

ERROR_STATUS = {
    AuctionNotFound: status.HTTP_404_NOT_FOUND,
    UserNotFound: status.HTTP_404_NOT_FOUND,
    AuctionNotActive: status.HTTP_409_CONFLICT,
    BidTooLow: status.HTTP_422_UNPROCESSABLE_CONTENT,
    BidNotAllowed: status.HTTP_403_FORBIDDEN,
    IdempotencyConflict: status.HTTP_409_CONFLICT,
}

ERROR_RESPONSES = {code: {"model": ErrorResponse} for code in (403, 404, 409, 422)}


def get_bid_service(db: Session = Depends(get_db)) -> BidService:
    return BidService(db)


def to_http_error(err: BidError) -> HTTPException:
    detail = {"code": err.code, "message": err.message}
    if isinstance(err, BidTooLow):
        detail["min_amount"] = err.min_amount
    return HTTPException(status_code=ERROR_STATUS.get(type(err), 400), detail=detail)


async def publish(outcome: BidOutcome) -> None:
    if outcome.bids and not outcome.duplicate:
        await manager.broadcast_to_auction(outcome.auction_id, outcome.to_event())


@router.post(
    "/auctions/{auction_id}/bids",
    response_model=BidResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Mükerrer istek: ilk sonucu döner"}, **ERROR_RESPONSES},
)
async def place_bid(
    auction_id: int,
    body: BidRequest,
    response: Response,
    idempotency_key: str = Header(..., min_length=1, max_length=100),
    user_id: int = Depends(current_user_id),
    service: BidService = Depends(get_bid_service),
):
    """Teklif verir. Aynı `Idempotency-Key` ile tekrar gönderilirse yeni teklif açılmaz."""
    try:
        # Servis bloklayan veritabanı çağrıları yapar; event loop'u tıkamamak
        # için ayrı thread'de çalışır.
        outcome = await run_in_threadpool(
            service.place_bid, auction_id, user_id, body.amount, idempotency_key
        )
    except BidError as err:
        raise to_http_error(err)

    if outcome.duplicate:
        response.status_code = status.HTTP_200_OK
    await publish(outcome)
    return outcome.to_response()


@router.put(
    "/auctions/{auction_id}/auto-bid",
    response_model=BidResponse,
    responses=ERROR_RESPONSES,
)
async def set_auto_bid(
    auction_id: int,
    body: AutoBidRequest,
    user_id: int = Depends(current_user_id),
    service: BidService = Depends(get_bid_service),
):
    """Otomatik teklif üst limitini kaydeder; gerekirse hemen teklif verir."""
    try:
        outcome = await run_in_threadpool(
            service.set_auto_bid_limit, auction_id, user_id, body.max_amount
        )
    except BidError as err:
        raise to_http_error(err)
    await publish(outcome)
    return outcome.to_response()


@router.get("/auctions/{auction_id}", response_model=AuctionState, responses=ERROR_RESPONSES)
async def get_auction(auction_id: int, service: BidService = Depends(get_bid_service)):
    """Anlık fiyat, bitiş zamanı, sunucu saati (geri sayım için) ve son teklifler."""
    try:
        return await run_in_threadpool(service.get_state, auction_id)
    except BidError as err:
        raise to_http_error(err)
