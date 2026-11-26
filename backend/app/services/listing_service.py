"""
İlan açma ve ilan kotası (doküman 4-A, 4-B, bölüm 6 ve 8).

Satıcılar yıllık üyelik planıyla çalışır: bireysel plan 20, profesyonel plan
200 ilan hakkı verir. Kota **sunucu tarafında** kontrol edilir; istemcinin
gönderdiği hiçbir bilgiye güvenilmez.

Kota kuralı:
    Bir üyelik dönemi boyunca o üyeliğe bağlı açılan her ilan bir hak tüketir
    (durumundan bağımsız). İlanı iptal edip yeniden açmak kotayı sıfırlamaz.

Eşzamanlılık:
    Kotanın son hakkı için aynı anda iki istek gelirse ikisi de "1 hak kaldı"
    görüp kotayı aşabilir. Bu yüzden ilan açılırken satıcının aktif üyelik
    satırı `SELECT ... FOR UPDATE` ile kilitlenir; sayım ve kayıt aynı işlemde
    yapılır (ADR-02 ile aynı yaklaşım).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Auction, AuditLog, Listing, Subscription, User
from app.services.errors import ListingQuotaExceeded, NoActiveSubscription, UserNotFound


@dataclass(frozen=True)
class ListingDraft:
    """Satıcının girdiği ilan ve açık artırma bilgileri (doğrulanmış)."""

    title: str
    start_price: int
    min_increment: int
    duration_minutes: int
    description: str | None = None
    defects: str | None = None
    category: str | None = None
    city: str | None = None
    district: str | None = None
    photos: list[str] | None = None
    safe_meeting_prefs: dict | None = None


@dataclass(frozen=True)
class QuotaStatus:
    subscription_id: int
    plan: str
    quota: int
    used: int
    ends_at: datetime

    @property
    def remaining(self) -> int:
        return max(0, self.quota - self.used)

    def to_dict(self) -> dict:
        return {
            "subscription_id": self.subscription_id,
            "plan": self.plan,
            "quota": self.quota,
            "used": self.used,
            "remaining": self.remaining,
            "ends_at": self.ends_at.isoformat(),
        }


@dataclass(frozen=True)
class CreatedListing:
    listing_id: int
    auction_id: int
    end_time: datetime
    quota: QuotaStatus

    def to_dict(self) -> dict:
        return {
            "listing_id": self.listing_id,
            "auction_id": self.auction_id,
            "end_time": self.end_time.isoformat(),
            "quota": self.quota.to_dict(),
        }


class ListingService:
    def __init__(self, db: Session):
        self.db = db

    def create_listing(self, seller_id: int, draft: ListingDraft) -> CreatedListing:
        """İlanı ve hemen başlayan açık artırmasını açar; kota doluysa reddeder."""
        try:
            self._get_user(seller_id)
            now = self._server_now()
            subscription = self._active_subscription(seller_id, now, lock=True)
            used = self._used(subscription.id)
            if used >= subscription.listing_quota:
                raise ListingQuotaExceeded(
                    f"İlan kotanız dolu ({used}/{subscription.listing_quota}). "
                    "Daha fazla ilan için profesyonel plana geçebilirsiniz.",
                    subscription.listing_quota,
                )

            listing = Listing(
                seller_id=seller_id,
                subscription_id=subscription.id,
                title=draft.title,
                description=draft.description,
                defects=draft.defects,
                category=draft.category,
                city=draft.city,
                district=draft.district,
                photos=draft.photos,
                safe_meeting_prefs=draft.safe_meeting_prefs,
                status="ACTIVE",
                created_at=now,
            )
            self.db.add(listing)
            self.db.flush()
            auction = Auction(
                listing_id=listing.id,
                start_price=draft.start_price,
                min_increment=draft.min_increment,
                current_price=draft.start_price,
                start_time=now,
                end_time=now + timedelta(minutes=draft.duration_minutes),
                status="ACTIVE",
            )
            self.db.add(auction)
            self.db.flush()
            self.db.add(AuditLog(
                actor_id=seller_id, action="LISTING_CREATED", entity="listing",
                entity_id=listing.id,
                data={"auction_id": auction.id, "subscription_id": subscription.id,
                      "quota_used": used + 1},
                created_at=now,
            ))

            result = CreatedListing(
                listing_id=listing.id,
                auction_id=auction.id,
                end_time=auction.end_time,
                quota=self._status(subscription, used + 1),
            )
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def quota_status(self, seller_id: int) -> QuotaStatus:
        """Satıcının aktif üyeliği ve kalan ilan hakkı (kilit almaz)."""
        self._get_user(seller_id)
        subscription = self._active_subscription(seller_id, self._server_now(), lock=False)
        return self._status(subscription, self._used(subscription.id))

    # ------------------------------------------------------------ yardımcılar
    def _get_user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise UserNotFound(f"Kullanıcı bulunamadı: {user_id}")
        return user

    def _server_now(self) -> datetime:
        return self.db.scalar(select(func.clock_timestamp()))

    def _active_subscription(self, seller_id: int, now: datetime, *, lock: bool) -> Subscription:
        query = (
            select(Subscription)
            .where(
                Subscription.user_id == seller_id,
                Subscription.status == "ACTIVE",
                Subscription.starts_at <= now,
                Subscription.ends_at > now,
            )
            .order_by(Subscription.ends_at.desc())
            .limit(1)
        )
        if lock:
            query = query.with_for_update()
        subscription = self.db.scalars(query).first()
        if subscription is None:
            raise NoActiveSubscription(
                "İlan açmak için aktif bir satıcı üyeliği gerekir (bireysel veya profesyonel)."
            )
        return subscription

    def _used(self, subscription_id: int) -> int:
        return self.db.scalar(
            select(func.count(Listing.id)).where(Listing.subscription_id == subscription_id)
        )

    @staticmethod
    def _status(subscription: Subscription, used: int) -> QuotaStatus:
        return QuotaStatus(
            subscription_id=subscription.id,
            plan=subscription.plan,
            quota=subscription.listing_quota,
            used=used,
            ends_at=subscription.ends_at,
        )
