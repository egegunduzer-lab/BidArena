from abc import ABC, abstractmethod


class ITrustScoreStrategy(ABC):
    @abstractmethod
    def calculate_score(self, trust_events: list) -> float:
        pass


class BuyerTrustStrategy(ITrustScoreStrategy):
    def calculate_score(self, trust_events: list) -> float:
        verified_events = [
            e for e in trust_events
            if e.get("verified", False) and e.get("party") == "BUYER"
        ]
        return float(sum(e.get("points", 0) for e in verified_events))


class SellerTrustStrategy(ITrustScoreStrategy):
    def calculate_score(self, trust_events: list) -> float:
        verified_events = [
            e for e in trust_events
            if e.get("verified", False) and e.get("party") == "SELLER"
        ]
        return float(sum(e.get("points", 0) for e in verified_events))
