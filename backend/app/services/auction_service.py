"""
Açık artırma kapanışı (doküman 4-C ve 4-D, ADR-03).

Süresi dolan açık artırmayı sunucu kapatır ve tek bir koşullu kazanan
belirler. Bu iş bir arka plan görevinden (app/core/scheduler.py) düzenli
aralıklarla çağrılır; HTTP isteğine bağlı değildir.

Teklif motoruyla yarış:
    Bitişten hemen önce gelen bir teklif süreyi uzatabilir (anti-sniping).
    Kapanış bu yüzden iki önlem alır:
      1. Satırı `FOR UPDATE SKIP LOCKED` ile kilitler. O anda bir teklif
         satırı kilitliyse beklemez, bu turu atlar; bir sonraki turda
         yeniden dener.
      2. Kilidi aldıktan sonra bitiş zamanını veritabanı saatiyle yeniden
         kontrol eder. Bekleme sırasında süre uzatılmışsa kapatmaz.
    Böylece "teklif kabul edildi ama açık artırma da kapandı" durumu oluşmaz.

Birden fazla sunucu süreci aynı anda çalışsa da her açık artırma bir kez
kapanır: kapanan satır CLOSED olur ve bir daha seçilmez.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    Appointment,
    Auction,
    AuditLog,
    AutoBidLimit,
    Bid,
    Notification,
    Watchlist,
)


@dataclass(frozen=True)
class ClosedAuction:
    auction_id: int
    winner_id: int | None
    final_price: int | None
    appointment_id: int | None
    closed_at: datetime

    def to_event(self) -> dict:
        return {
            "event": "AUCTION_CLOSED",
            "auction_id": self.auction_id,
            "winner_id": self.winner_id,
            "final_price": self.final_price,
            "closed_at": self.closed_at.isoformat(),
        }


@dataclass
class CloserRun:
    """Bir kapanış turunun sonucu."""

    started: list[int] = field(default_factory=list)
    closed: list[ClosedAuction] = field(default_factory=list)


class AuctionCloser:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        # Her açık artırma kendi kısa işleminde kapatılır; bu yüzden tek bir
        # oturum yerine oturum üreten bir fabrika alınır.
        self.session_factory = session_factory

    def run_once(self) -> CloserRun:
        """Başlama saati gelenleri aktifleştirir, süresi dolanları kapatır."""
        run = CloserRun(started=self.start_due_auctions())
        for auction_id in self._expired_auction_ids():
            closed = self.close_auction(auction_id)
            if closed is not None:
                run.closed.append(closed)
        return run

    def start_due_auctions(self) -> list[int]:
        with self.session_factory() as db:
            ids = db.scalars(
                update(Auction)
                .where(
                    Auction.status == "SCHEDULED",
                    Auction.start_time <= func.clock_timestamp(),
                    Auction.end_time > func.clock_timestamp(),
                )
                .values(status="ACTIVE")
                .returning(Auction.id)
            ).all()
            db.commit()
            return list(ids)

    def close_auction(self, auction_id: int) -> ClosedAuction | None:
        """Tek bir açık artırmayı kapatır. Kapatamazsa (kilitli, süresi
        uzamış ya da zaten kapalı) None döner."""
        with self.session_factory() as db:
            try:
                auction = db.execute(
                    select(Auction)
                    .where(Auction.id == auction_id, Auction.status != "CLOSED")
                    .with_for_update(skip_locked=True)
                ).scalar_one_or_none()
                if auction is None:
                    return None

                now = db.scalar(select(func.clock_timestamp()))
                if auction.end_time > now:
                    # Kilit beklenirken bir teklif süreyi uzatmış olabilir.
                    db.rollback()
                    return None

                closed = self._close(db, auction, now)
                db.commit()
                return closed
            except Exception:
                db.rollback()
                raise

    # ------------------------------------------------------------ iç adımlar
    def _expired_auction_ids(self) -> list[int]:
        with self.session_factory() as db:
            return list(
                db.scalars(
                    select(Auction.id)
                    .where(
                        Auction.status.in_(("SCHEDULED", "ACTIVE")),
                        Auction.end_time <= func.clock_timestamp(),
                    )
                    .order_by(Auction.end_time)
                ).all()
            )

    def _close(self, db: Session, auction: Auction, now: datetime) -> ClosedAuction:
        seller_id = auction.listing.seller_id
        winning_bid: Bid | None = auction.highest_bid

        auction.status = "CLOSED"
        db.execute(
            update(AutoBidLimit)
            .where(AutoBidLimit.auction_id == auction.id)
            .values(is_active=False)
        )

        appointment = None
        winner_id = None
        if winning_bid is not None:
            winner_id = winning_bid.bidder_id
            auction.winner_id = winner_id
            # Ürün satıldı sayılmaz; teslimat tamamlanana kadar ilan kapalı kalır.
            auction.listing.status = "CLOSED"
            # Koşullu kazanan: buluşma randevusu taslağı açılır (doküman 4-D).
            appointment = Appointment(
                auction_id=auction.id,
                buyer_id=winner_id,
                seller_id=seller_id,
                agreed_price=winning_bid.amount,
                status="PROPOSED",
            )
            db.add(appointment)
            db.flush()
        # Teklif gelmediyse ilan ACTIVE kalır; satıcı yeniden açık artırmaya çıkarabilir.

        self._notify(db, auction, seller_id, winner_id, appointment)
        db.add(
            AuditLog(
                actor_id=None,
                action="AUCTION_CLOSED",
                entity="auction",
                entity_id=auction.id,
                data={
                    "winner_id": winner_id,
                    "price": winning_bid.amount if winning_bid else None,
                    "appointment_id": appointment.id if appointment else None,
                },
                created_at=now,
            )
        )
        return ClosedAuction(
            auction_id=auction.id,
            winner_id=winner_id,
            final_price=winning_bid.amount if winning_bid else None,
            appointment_id=appointment.id if appointment else None,
            closed_at=now,
        )

    def _notify(
        self,
        db: Session,
        auction: Auction,
        seller_id: int,
        winner_id: int | None,
        appointment: Appointment | None,
    ) -> None:
        """Doküman 4-H: kazanma, açık artırma bitişi ve takip bildirimleri."""
        price = auction.current_price if winner_id else None

        def notify(user_id: int, type_: str, **extra):
            db.add(Notification(
                user_id=user_id, type=type_,
                payload={"auction_id": auction.id, "price": price, **extra},
            ))

        notified = {seller_id}
        notify(seller_id, "AUCTION_ENDED", winner_id=winner_id)
        if winner_id is not None:
            notify(winner_id, "AUCTION_WON", appointment_id=appointment.id)
            notified.add(winner_id)

        bidders = db.scalars(
            select(Bid.bidder_id).where(Bid.auction_id == auction.id).distinct()
        ).all()
        for user_id in bidders:
            if user_id not in notified:
                notify(user_id, "AUCTION_LOST")
                notified.add(user_id)

        watchers = db.scalars(
            select(Watchlist.user_id).where(Watchlist.listing_id == auction.listing_id)
        ).all()
        for user_id in watchers:
            if user_id not in notified:
                notify(user_id, "AUCTION_ENDED", winner_id=winner_id)
                notified.add(user_id)
