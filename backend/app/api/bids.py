"""
Teklif uÃ§ noktalarÄ± (REST).

Bu katman yalnÄ±zca HTTP ile ilgilenir: girdiyi doÄŸrular, servisi Ã§aÄŸÄ±rÄ±r,
iÅŸ kuralÄ± hatalarÄ±nÄ± HTTP kodlarÄ±na Ã§evirir ve iÅŸlem commit edildikten
SONRA yeni durumu WebSocket ile yayÄ±nlar. Kural mantÄ±ÄŸÄ± BidService'tedir.

Kimlik doÄŸrulama modÃ¼lÃ¼ henÃ¼z yok; teklif veren kullanÄ±cÄ± geÃ§ici olarak
`X-User-Id` baÅŸlÄ±ÄŸÄ±yla belirtilir. Auth eklendiÄŸinde yalnÄ±zca
`current_user_id` baÄŸÄ±mlÄ±lÄ±ÄŸÄ± deÄŸiÅŸecek, servis kodu deÄŸiÅŸmeyecek.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

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

router = APIRouter(tags=["AÃ§Ä±k artÄ±rma ve teklifler"])

ERROR_STATUS = {
    AuctionNotFound: status.HTTP_404_NOT_FOUND,
    UserNotFound: status.HTTP_404_NOT_FOUND,
    AuctionNotActive: status.HTTP_409_CONFLICT,
    BidTooLow: status.HTTP_422_UNPROCESSABLE_CONTENT,
    BidNotAllowed: status.HTTP_403_FORBIDDEN,
    IdempotencyConflict: status.HTTP_409_CONFLICT,
}

ERROR_RESPONSES = {code: {"model": ErrorResponse} for code in (403, 404, 409, 422)}


def current_user_id(x_user_id: int = Header(..., description="GeÃ§ici: teklif veren kullanÄ±cÄ±")) -> int:
    return x_user_id


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
    responses={200: {"description": "MÃ¼kerrer istek: ilk sonucu dÃ¶ner"}, **ERROR_RESPONSES},
)
async def place_bid(
    auction_id: int,
    body: BidRequest,
    response: Response,
    idempotency_key: str = Header(..., min_length=1, max_length=100),
    user_id: int = Depends(current_user_id),
    service: BidService = Depends(get_bid_service),
):
    """Teklif verir. AynÄ± `Idempotency-Key` ile tekrar gÃ¶nderilirse yeni teklif aÃ§Ä±lmaz."""
    try:
        # Servis bloklayan veritabanÄ± Ã§aÄŸrÄ±larÄ± yapar; event loop'u tÄ±kamamak
        # iÃ§in ayrÄ± thread'de Ã§alÄ±ÅŸÄ±r.
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
    """Otomatik teklif Ã¼st limitini kaydeder; gerekirse hemen teklif verir."""
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
    """AnlÄ±k fiyat, bitiÅŸ zamanÄ±, sunucu saati (geri sayÄ±m iÃ§in) ve son teklifler."""
    try:
        return await run_in_threadpool(service.get_state, auction_id)
    except BidError as err:
        raise to_http_error(err)
