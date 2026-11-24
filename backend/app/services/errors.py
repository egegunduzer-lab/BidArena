"""
Teklif motorunun iş kuralı hataları.

Servis katmanı HTTP bilmez; kural ihlallerini bu istisnalarla bildirir.
API katmanı (app/api/bids.py) her istisnayı uygun HTTP koduna çevirir.
Böylece aynı servis REST, WebSocket veya testlerden aynı şekilde çağrılabilir.
"""


class BidError(Exception):
    """Tüm teklif hatalarının temel sınıfı."""

    code = "BID_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AuctionNotFound(BidError):
    code = "AUCTION_NOT_FOUND"


class UserNotFound(BidError):
    code = "USER_NOT_FOUND"


class AuctionNotActive(BidError):
    """Açık artırma henüz başlamadı ya da sunucu saatine göre bitti."""

    code = "AUCTION_NOT_ACTIVE"


class BidTooLow(BidError):
    """Teklif, başlangıç fiyatının veya minimum artışın altında."""

    code = "BID_TOO_LOW"

    def __init__(self, message: str, min_amount: int):
        super().__init__(message)
        self.min_amount = min_amount


class BidNotAllowed(BidError):
    """Kullanıcı bu açık artırmaya teklif veremez (satıcı, kısıtlı, zaten önde vb.)."""

    code = "BID_NOT_ALLOWED"


class IdempotencyConflict(BidError):
    """Aynı idempotency anahtarı farklı bir teklif için yeniden kullanıldı."""

    code = "IDEMPOTENCY_CONFLICT"
