from abc import ABC, abstractmethod

# 1. Ortak Arayüz (Interface)
class ITrustScoreStrategy(ABC):
    @abstractmethod
    def calculate_score(self, user_data: dict) -> float:
        pass

# 2. Alıcı Güven Skoru Stratejisi
class BuyerTrustStrategy(ITrustScoreStrategy):
    def calculate_score(self, user_data: dict) -> float:
        # Alıcıya özel puanlama mantığı (örn: başarılı ihale katılımı, ödeme hızı vb.)
        completed_bids = user_data.get("completed_bids", 0)
        return float(completed_bids * 10)

# 3. Satıcı Güven Skoru Stratejisi
class SellerTrustStrategy(ITrustScoreStrategy):
    def calculate_score(self, user_data: dict) -> float:
        # Satıcıya özel puanlama mantığı (örn: kusursuz ilan, zamanında teslimat vb.)
        successful_sales = user_data.get("successful_sales", 0)
        return float(successful_sales * 15)