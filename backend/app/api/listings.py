"""İlan açma ve satıcı ilan kotası uç noktaları."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import current_user_id
from app.core.database import get_db
from app.schemas import ErrorResponse, ListingCreate, ListingCreated, QuotaOut
from app.services.errors import (
    DomainError,
    ListingQuotaExceeded,
    NoActiveSubscription,
    UserNotFound,
)
from app.services.listing_service import ListingDraft, ListingService

router = APIRouter(tags=["İlanlar ve üyelik"])

ERROR_STATUS = {
    UserNotFound: status.HTTP_404_NOT_FOUND,
    NoActiveSubscription: status.HTTP_403_FORBIDDEN,
    ListingQuotaExceeded: status.HTTP_403_FORBIDDEN,
}
ERROR_RESPONSES = {code: {"model": ErrorResponse} for code in (403, 404)}


def get_listing_service(db: Session = Depends(get_db)) -> ListingService:
    return ListingService(db)


def to_http_error(err: DomainError) -> HTTPException:
    detail = {"code": err.code, "message": err.message}
    if isinstance(err, ListingQuotaExceeded):
        detail["quota"] = err.quota
    return HTTPException(status_code=ERROR_STATUS.get(type(err), 400), detail=detail)


@router.post(
    "/listings",
    response_model=ListingCreated,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def create_listing(
    body: ListingCreate,
    user_id: int = Depends(current_user_id),
    service: ListingService = Depends(get_listing_service),
):
    """İlan ve hemen başlayan açık artırmasını açar. Aktif üyelik ve boş kota gerekir."""
    try:
        created = await run_in_threadpool(
            service.create_listing, user_id, ListingDraft(**body.model_dump())
        )
    except DomainError as err:
        raise to_http_error(err)
    return created.to_dict()


@router.get("/sellers/me/quota", response_model=QuotaOut, responses=ERROR_RESPONSES)
async def my_quota(
    user_id: int = Depends(current_user_id),
    service: ListingService = Depends(get_listing_service),
):
    """Satıcının aktif üyelik planı, ilan kotası ve kalan hakkı."""
    try:
        status_ = await run_in_threadpool(service.quota_status, user_id)
    except DomainError as err:
        raise to_http_error(err)
    return status_.to_dict()
