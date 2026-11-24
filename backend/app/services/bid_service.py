"""
Teklif motoru (doküman bölüm 4-C).

Bir teklifin kabul edilip edilmeyeceğine ve kabul edilirse açık artırmanın
nasıl değişeceğine bu sınıf karar verir. HTTP veya WebSocket bilmez; API
katmanı yalnızca bu servisi çağırır ve sonucu yayınlar.

Eşzamanlılık (ADR-02):
    Her işlem açık artırma satırını `SELECT ... FOR UPDATE` ile kilitler.
    Aynı açık artırmaya gelen teklifler böylece sırayla işlenir; iki teklif
    aynı "güncel fiyatı" görüp ikisi birden kabul edilemez. Kilit, commit veya
    rollback ile bırakılır.

Saat:
    Bitiş kontrolü ve süre uzatma, uygulama sunucusunun değil veritabanı
    sunucusunun saatiyle (clock_timestamp) yapılır. Kilit beklenirken geçen
    süre de hesaba katılır; istemcinin saati hiçbir zaman kullanılmaz.

Mükerrer istek (idempotency):
    Her teklif (bidder_id, idempotency_key) çiftiyle gelir ve veritabanında bu
    çift tekildir. Aynı istek tekrar gelirse yeni kayıt açılmaz, ilk sonuç
    döner. Kontrol kilit alındıktan sonra yapılır; aynı anda gelen iki kopya da
    sıraya girer ve ikincisi birincinin kaydını görür.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Auction, AuditLog, AutoBidLimit, Bid, Notification, User
from app.services.errors import (
    AuctionNotActive,
    AuctionNotFound,
    BidNotAllowed,
    BidTooLow,
    IdempotencyConflict,
    UserNotFound,
)

# Otomatik teklif çözümlemesinde güvenlik sınırı. Her turda fiyat kesin olarak
# arttığı için döngü zaten sonlanır; bu sınır yalnızca beklenmedik veriye karşı.
MAX_AUTO_BID_ROUNDS = 50


@dataclass(frozen=True)
class BidPolicy:
    """Değiştirilebilir iş kuralı parametreleri.

    Servis bu nesneyi dışarıdan alır (dependency injection). Kurallar
    değişince servis kodu değişmez, yalnızca farklı bir politika verilir.
    """

    # Doküman 4-G: yeni (doğrulanmamış) hesaplar için teklif sınırı.
    unverified_max_bid: int = 20_000


@dataclass(frozen=True)
class PlacedBid:
    id: int
    bidder_id: int
    amount: int
    is_auto: bool
    created_at: datetime

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bidder_id": self.bidder_id,
            "amount": self.amount,
            "is_auto": self.is_auto,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class BidOutcome:
    """Bir teklif işleminin sonucu; yayınlanacak olayın da kaynağı."""

    auction_id: int
    current_price: int
    min_next_bid: int
    highest_bidder_id: int | None
    end_time: datetime
    server_time: datetime
    extended: bool = False
    duplicate: bool = False
    bids: list[PlacedBid] = field(default_factory=list)

    def to_event(self) -> dict:
        """WebSocket ile tüm izleyicilere gönderilecek mesaj."""
        return {
            "event": "NEW_BID",
            "auction_id": self.auction_id,
            "current_price": self.current_price,
            "min_next_bid": self.min_next_bid,
            "highest_bidder_id": self.highest_bidder_id,
            "end_time": self.end_time.isoformat(),
            "server_time": self.server_time.isoformat(),
            "extended": self.extended,
            "bids": [b.to_dict() for b in self.bids],
        }

    def to_response(self) -> dict:
        """Teklifi gönderen istemciye dönen yanıt (yayın + mükerrer bilgisi)."""
        return {**self.to_event(), "duplicate": self.duplicate}


class BidService:
    def __init__(self, db: Session, policy: BidPolicy | None = None):
        self.db = db
        self.policy = policy or BidPolicy()

    # ------------------------------------------------------------ dış arayüz
    def place_bid(
        self, auction_id: int, bidder_id: int, amount: int, idempotency_key: str
    ) -> BidOutcome:
        """Elle verilen teklifi işler; gerekirse otomatik karşı teklifleri ekler."""
        try:
            auction = self._lock_auction(auction_id)
            now = self._server_now()

            existing = self.db.scalar(
                select(Bid).where(
                    Bid.bidder_id == bidder_id, Bid.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                if existing.auction_id != auction_id or existing.amount != amount:
                    raise IdempotencyConflict(
                        "Bu idempotency anahtarı başka bir teklif için kullanılmış."
                    )
                outcome = self._outcome(auction, now, duplicate=True)
                self.db.rollback()
                return outcome

            self._ensure_active(auction, now)
            bidder = self._get_user(bidder_id)
            self._ensure_can_bid(bidder, auction, amount, now)

            minimum = self._min_next_bid(auction)
            if amount < minimum:
                raise BidTooLow(f"Teklif en az {minimum} TL olmalı.", minimum)
            if self._leader_id(auction) == bidder_id:
                raise BidNotAllowed("En yüksek teklif zaten sizde.")

            previous_leader = self._leader_id(auction)
            placed = [self._record_bid(auction, bidder_id, amount, False, idempotency_key, now)]
            placed += self._resolve_auto_bids(auction, now)
            extended = self._maybe_extend(auction, now)
            self._notify_outbid(auction, previous_leader, placed)

            outcome = self._outcome(auction, now, extended=extended, bids=placed)
            self.db.commit()
            return outcome
        except Exception:
            self.db.rollback()
            raise

    def set_auto_bid_limit(self, auction_id: int, user_id: int, max_amount: int) -> BidOutcome:
        """Otomatik teklif üst limitini kaydeder ve hemen uygular.

        Kullanıcı önde değilse sistem onun adına gereken en düşük teklifi verir;
        başka bir otomatik limit varsa ikisi limitler dahilinde yarışır.
        """
        try:
            auction = self._lock_auction(auction_id)
            now = self._server_now()
            self._ensure_active(auction, now)
            user = self._get_user(user_id)
            self._ensure_can_bid(user, auction, max_amount, now)

            leader = self._leader_id(auction)
            required = auction.current_price if leader == user_id else self._min_next_bid(auction)
            if max_amount < required:
                raise BidTooLow(f"Üst limit en az {required} TL olmalı.", required)

            limit = self.db.scalar(
                select(AutoBidLimit).where(
                    AutoBidLimit.auction_id == auction_id, AutoBidLimit.user_id == user_id
                )
            )
            if limit is None:
                limit = AutoBidLimit(auction_id=auction_id, user_id=user_id, created_at=now)
                self.db.add(limit)
            limit.max_amount = max_amount
            limit.is_active = True
            self.db.flush()

            placed = self._resolve_auto_bids(auction, now)
            extended = self._maybe_extend(auction, now) if placed else False
            self._notify_outbid(auction, leader, placed)

            outcome = self._outcome(auction, now, extended=extended, bids=placed)
            self.db.commit()
            return outcome
        except Exception:
            self.db.rollback()
            raise

    def get_state(self, auction_id: int, history: int = 20) -> dict:
        """Açık artırmanın anlık durumu ve son teklifler (kilit almaz)."""
        auction = self.db.get(Auction, auction_id)
        if auction is None:
            raise AuctionNotFound(f"Açık artırma bulunamadı: {auction_id}")
        now = self._server_now()
        recent = self.db.scalars(
            select(Bid).where(Bid.auction_id == auction_id).order_by(Bid.id.desc()).limit(history)
        ).all()
        state = self._outcome(auction, now, bids=[self._to_placed(b) for b in recent]).to_event()
        state["event"] = "SNAPSHOT"
        state["status"] = auction.status
        state["start_price"] = auction.start_price
        state["min_increment"] = auction.min_increment
        return state

    # ------------------------------------------------------------ kurallar
    def _lock_auction(self, auction_id: int) -> Auction:
        auction = self.db.execute(
            select(Auction).where(Auction.id == auction_id).with_for_update()
        ).scalar_one_or_none()
        if auction is None:
            raise AuctionNotFound(f"Açık artırma bulunamadı: {auction_id}")
        return auction

    def _server_now(self) -> datetime:
        # now() işlemin başladığı anı verir; kilit beklerken geçen süreyi
        # de saymak için gerçek anlık saat (clock_timestamp) kullanılır.
        return self.db.scalar(select(func.clock_timestamp()))

    def _ensure_active(self, auction: Auction, now: datetime) -> None:
        if auction.status == "CLOSED":
            raise AuctionNotActive("Açık artırma kapandı.")
        if now < auction.start_time:
            raise AuctionNotActive("Açık artırma henüz başlamadı.")
        if now >= auction.end_time:
            raise AuctionNotActive("Açık artırmanın süresi doldu.")
        if auction.status == "SCHEDULED":
            # Başlangıç saati geçmiş planlı açık artırma ilk teklifle aktifleşir.
            auction.status = "ACTIVE"

    def _get_user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise UserNotFound(f"Kullanıcı bulunamadı: {user_id}")
        return user

    def _ensure_can_bid(self, user: User, auction: Auction, amount: int, now: datetime) -> None:
        if user.id == auction.listing.seller_id:
            raise BidNotAllowed("Satıcı kendi ilanına teklif veremez.")
        if user.restricted_until is not None and user.restricted_until > now:
            raise BidNotAllowed(
                f"Hesabınız geçici olarak kısıtlı: {user.restriction_reason or 'gerekçe yok'}"
            )
        if not user.is_verified and amount > self.policy.unverified_max_bid:
            raise BidNotAllowed(
                f"Doğrulanmamış hesaplar en fazla {self.policy.unverified_max_bid} TL teklif verebilir."
            )

    def _min_next_bid(self, auction: Auction) -> int:
        if auction.highest_bid_id is None:
            return auction.start_price
        return auction.current_price + auction.min_increment

    def _leader_id(self, auction: Auction) -> int | None:
        return auction.highest_bid.bidder_id if auction.highest_bid is not None else None

    # ------------------------------------------------------------ değişiklikler
    def _record_bid(
        self, auction: Auction, bidder_id: int, amount: int, is_auto: bool, key: str, now: datetime
    ) -> PlacedBid:
        bid = Bid(
            auction_id=auction.id,
            bidder_id=bidder_id,
            amount=amount,
            is_auto=is_auto,
            idempotency_key=key,
            created_at=now,
        )
        self.db.add(bid)
        self.db.flush()
        auction.current_price = amount
        auction.highest_bid = bid
        auction.highest_bid_id = bid.id
        return self._to_placed(bid)

    def _resolve_auto_bids(self, auction: Auction, now: datetime) -> list[PlacedBid]:
        """Otomatik teklif limitlerini, fiyat dengeye gelene kadar uygular.

        Her turda önde olmayan ve limiti yeterli olan en güçlü otomatik teklif
        sahibi seçilir. Rakiplerini geçmeye yetecek en düşük tutarı verir:
        rakiplerin en yüksek tavanı + minimum artış (kendi limitini aşmadan).
        """
        placed: list[PlacedBid] = []
        for _ in range(MAX_AUTO_BID_ROUNDS):
            limits = self.db.scalars(
                select(AutoBidLimit)
                .where(AutoBidLimit.auction_id == auction.id, AutoBidLimit.is_active.is_(True))
                .order_by(AutoBidLimit.max_amount.desc(), AutoBidLimit.created_at, AutoBidLimit.id)
            ).all()
            leader = self._leader_id(auction)
            minimum = self._min_next_bid(auction)

            challenger = None
            for limit in limits:
                if limit.user_id == leader or limit.max_amount < minimum:
                    continue
                try:
                    self._ensure_can_bid(self._get_user(limit.user_id), auction, minimum, now)
                except BidNotAllowed:
                    continue
                challenger = limit
                break
            if challenger is None:
                return placed

            rival_ceiling = max(
                [auction.current_price]
                + [l.max_amount for l in limits if l.user_id != challenger.user_id]
            )
            amount = min(challenger.max_amount, max(minimum, rival_ceiling + auction.min_increment))
            key = f"auto-{auction.id}-{challenger.user_id}-{amount}"
            placed.append(self._record_bid(auction, challenger.user_id, amount, True, key, now))
        return placed

    def _maybe_extend(self, auction: Auction, now: datetime) -> bool:
        """Anti-sniping: son pencerede gelen geçerli teklif süreyi uzatır."""
        window = timedelta(seconds=auction.extension_window_sec)
        if auction.end_time - now > window:
            return False
        auction.end_time = auction.end_time + timedelta(seconds=auction.extension_sec)
        auction.extension_count += 1
        self.db.add(
            AuditLog(
                actor_id=None,
                action="AUCTION_EXTENDED",
                entity="auction",
                entity_id=auction.id,
                data={
                    "extension_sec": auction.extension_sec,
                    "new_end_time": auction.end_time.isoformat(),
                },
                created_at=now,
            )
        )
        return True

    def _notify_outbid(self, auction: Auction, previous_leader: int | None, placed: list[PlacedBid]) -> None:
        """Geçilen teklif sahiplerine OUTBID bildirimi bırakır (doküman 4-H)."""
        final_leader = self._leader_id(auction)
        outbid = [previous_leader] + [b.bidder_id for b in placed]
        for user_id in dict.fromkeys(outbid):
            if user_id is None or user_id == final_leader:
                continue
            self.db.add(
                Notification(
                    user_id=user_id,
                    type="OUTBID",
                    payload={"auction_id": auction.id, "new_price": auction.current_price},
                )
            )

    # ------------------------------------------------------------ yardımcılar
    def _outcome(
        self,
        auction: Auction,
        now: datetime,
        *,
        extended: bool = False,
        duplicate: bool = False,
        bids: list[PlacedBid] | None = None,
    ) -> BidOutcome:
        return BidOutcome(
            auction_id=auction.id,
            current_price=auction.current_price,
            min_next_bid=self._min_next_bid(auction),
            highest_bidder_id=self._leader_id(auction),
            end_time=auction.end_time,
            server_time=now,
            extended=extended,
            duplicate=duplicate,
            bids=bids or [],
        )

    @staticmethod
    def _to_placed(bid: Bid) -> PlacedBid:
        return PlacedBid(
            id=bid.id,
            bidder_id=bid.bidder_id,
            amount=bid.amount,
            is_auto=bid.is_auto,
            created_at=bid.created_at,
        )
