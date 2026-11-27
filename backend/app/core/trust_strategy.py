from abc import ABC, abstractmethod

# 1. Ortak Arayüz (Interface)
class ITrustScoreStrategy(ABC):
    @abstractmethod
    def calculate_score(self, trust_events: list) -> float:
        pass

# 2. Alıcı Güven Skoru Stratejisi
class BuyerTrustStrategy(ITrustScoreStrategy):
    def calculate_score(self, trust_events: list) -> float:
        # Alıcıya özel puanlama mantığı (örn: başarılı ihale katılımı, ödeme hızı vb.)
        verified_events = [e for e in trust_events if e.get("verified", False) and e.get("role") == "BUYER"]
        return float(len(verified_events) * 10)

# 3. Satıcı Güven Skoru Stratejisi
class SellerTrustStrategy(ITrustScoreStrategy):
    def calculate_score(self, trust_events: list) -> float:
        # Satıcıya özel puanlama mantığı (örn: kusursuz ilan, zamanında teslimat vb.)
        verified_events = [e for e in trust_events if e.get("verified", False) and e.get("role") == "SELLER"]
        return float(len(verified_events) * 15)