"""
BidArena veritabanı modelleri (SQLAlchemy).

docs/schema.sql içindeki 15 tablonun Python karşılıklarıdır. Tabloları ve
kuralları (CHECK, unique index, trigger) schema.sql tanımlar; bu dosya sadece
backend'in o tablolarla konuşabilmesini sağlar. Şemada bir değişiklik olursa
buradaki ilgili sınıf da güncellenmelidir (backend/check_db.py farkı yakalar).

Sık kullanılacak örnekler:

    from sqlalchemy import select
    from app.models import Auction, Bid

    # Bir açık artırmanın en yüksek teklifi
    db.scalars(select(Bid).where(Bid.auction_id == 1)
               .order_by(Bid.amount.desc())).first()

    # Pessimistic locking (ADR-02): teklif işlenirken satırı kilitle
    auction = db.execute(
        select(Auction).where(Auction.id == auction_id).with_for_update()
    ).scalar_one()
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base

NOW = text("now()")


# ------------------------------------------------------------------ Kullanıcılar
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String)
    role = Column(String, nullable=False, server_default=text("'USER'"))  # USER | ADMIN
    is_verified = Column(Boolean, nullable=False, server_default=text("false"))
    restricted_until = Column(DateTime(timezone=True))  # gerekçeli geçici kısıt
    restriction_reason = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan = Column(String, nullable=False)  # INDIVIDUAL | PROFESSIONAL
    listing_quota = Column(Integer, nullable=False)
    price_tl = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # ACTIVE | EXPIRED | CANCELLED
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    payment_ref = Column(String)  # simüle ödeme kodu

    user = relationship("User")


# ------------------------------------------------------------------ İlanlar
class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    defects = Column(Text)  # ürün kusurları
    category = Column(String)
    city = Column(String)
    district = Column(String)
    photos = Column(JSONB)  # ["https://...jpg", ...]
    safe_meeting_prefs = Column(JSONB)
    status = Column(String, nullable=False, server_default=text("'DRAFT'"))  # DRAFT | ACTIVE | CLOSED | CANCELLED
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)

    seller = relationship("User")
    subscription = relationship("Subscription")
    auctions = relationship("Auction", back_populates="listing")


class Watchlist(Base):
    __tablename__ = "watchlist"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)


# ------------------------------------------------------------------ Açık artırma ve teklifler
class Auction(Base):
    __tablename__ = "auctions"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False)
    start_price = Column(Integer, nullable=False)
    min_increment = Column(Integer, nullable=False)
    current_price = Column(Integer, nullable=False)
    # auctions <-> bids karşılıklı bağlı; şemadaki gibi ertelenmiş (DEFERRED) foreign key
    highest_bid_id = Column(
        Integer,
        ForeignKey("bids.id", use_alter=True, deferrable=True, initially="DEFERRED"),
    )
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    extension_count = Column(Integer, nullable=False, server_default=text("0"))
    extension_window_sec = Column(Integer, nullable=False, server_default=text("120"))  # son kaç saniyede uzar
    extension_sec = Column(Integer, nullable=False, server_default=text("120"))  # ne kadar uzar
    status = Column(String, nullable=False, server_default=text("'SCHEDULED'"))  # SCHEDULED | ACTIVE | CLOSED
    winner_id = Column(Integer, ForeignKey("users.id"))

    listing = relationship("Listing", back_populates="auctions")
    bids = relationship("Bid", foreign_keys="Bid.auction_id", back_populates="auction")
    highest_bid = relationship("Bid", foreign_keys=[highest_bid_id], post_update=True)
    winner = relationship("User")


class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True)
    auction_id = Column(Integer, ForeignKey("auctions.id"), nullable=False)
    bidder_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Integer, nullable=False)  # TL, tam sayı
    is_auto = Column(Boolean, nullable=False, server_default=text("false"))
    idempotency_key = Column(String, nullable=False)  # (bidder_id, idempotency_key) tekil
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)

    auction = relationship("Auction", foreign_keys=[auction_id], back_populates="bids")
    bidder = relationship("User")


class AutoBidLimit(Base):
    __tablename__ = "auto_bid_limits"

    id = Column(Integer, primary_key=True)
    auction_id = Column(Integer, ForeignKey("auctions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    max_amount = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)


# ------------------------------------------------------------------ Buluşma ve teslim
class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    auction_id = Column(Integer, ForeignKey("auctions.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    agreed_price = Column(Integer, nullable=False)
    location = Column(String)
    meeting_time = Column(DateTime(timezone=True))
    buyer_accepted = Column(Boolean, nullable=False, server_default=text("false"))
    seller_accepted = Column(Boolean, nullable=False, server_default=text("false"))
    otp_hash = Column(String)
    otp_expires_at = Column(DateTime(timezone=True))
    otp_used_at = Column(DateTime(timezone=True))
    otp_failed_attempts = Column(Integer, nullable=False, server_default=text("0"))
    # PROPOSED | CONFIRMED | MATCHED | COMPLETED | NO_SHOW_BUYER | NO_SHOW_SELLER
    # | ITEM_MISMATCH | CANCELLED | DISPUTED
    # Not: COMPLETED için iki taraf da delivery_confirmations'a kayıt atmış olmalı (trigger).
    status = Column(String, nullable=False, server_default=text("'PROPOSED'"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)

    auction = relationship("Auction")
    buyer = relationship("User", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])
    confirmations = relationship("DeliveryConfirmation", back_populates="appointment")
    disputes = relationship("Dispute", back_populates="appointment")


class DeliveryConfirmation(Base):
    __tablename__ = "delivery_confirmations"

    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    party = Column(String, nullable=False)  # BUYER | SELLER
    confirmed_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)

    appointment = relationship("Appointment", back_populates="confirmations")


# ------------------------------------------------------------------ Uyuşmazlık ve güven
class Dispute(Base):
    __tablename__ = "disputes"

    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False)
    opened_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    against_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)  # NO_SHOW | ITEM_MISMATCH | OTHER
    description = Column(Text)
    # OPEN | UNDER_REVIEW | UPHELD | REJECTED | APPEALED | CLOSED
    status = Column(String, nullable=False, server_default=text("'OPEN'"))
    resolution_note = Column(Text)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    appeal_note = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)
    resolved_at = Column(DateTime(timezone=True))

    appointment = relationship("Appointment", back_populates="disputes")
    evidence = relationship("Evidence", back_populates="dispute")


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True)
    dispute_id = Column(Integer, ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_url = Column(String, nullable=False)
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)

    dispute = relationship("Dispute", back_populates="evidence")


class TrustEvent(Base):
    __tablename__ = "trust_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    party = Column(String, nullable=False)  # BUYER | SELLER
    type = Column(String, nullable=False)  # SALE_COMPLETED | NO_SHOW | ITEM_MISMATCH
    points = Column(Integer, nullable=False)  # artı veya eksi puan
    verified = Column(Boolean, nullable=False, server_default=text("false"))  # sadece doğrulanmışlar puanı etkiler
    appointment_id = Column(Integer, ForeignKey("appointments.id"))
    dispute_id = Column(Integer, ForeignKey("disputes.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)


class BackupOffer(Base):
    __tablename__ = "backup_offers"

    id = Column(Integer, primary_key=True)
    auction_id = Column(Integer, ForeignKey("auctions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    bid_id = Column(Integer, ForeignKey("bids.id"), nullable=False)
    price = Column(Integer, nullable=False)
    rank = Column(Integer, nullable=False)  # 1 = kazanandan sonraki ilk sıra
    status = Column(String, nullable=False, server_default=text("'PENDING'"))  # PENDING | ACCEPTED | REJECTED | EXPIRED
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)
    responded_at = Column(DateTime(timezone=True))


# ------------------------------------------------------------------ Bildirim ve denetim
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # OUTBID, AUCTION_WON, BACKUP_OFFER, ...
    payload = Column(JSONB)
    is_read = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id"))  # NULL = sistem
    action = Column(String, nullable=False)
    entity = Column(String, nullable=False)
    entity_id = Column(Integer)
    data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=NOW)
