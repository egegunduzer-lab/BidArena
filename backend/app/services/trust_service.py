from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.trust_strategy import BuyerTrustStrategy, SellerTrustStrategy
from app.models import TrustEvent


class TrustScoreService:
    def __init__(self, db: Session):
        self.db = db

    def calculate_score(self, user_id: int, party: str) -> float:
        strategies = {
            "BUYER": BuyerTrustStrategy,
            "SELLER": SellerTrustStrategy,
        }
        strategy_class = strategies.get(party)
        if strategy_class is None:
            raise ValueError("party BUYER veya SELLER olmalı")

        records = self.db.scalars(
            select(TrustEvent).where(TrustEvent.user_id == user_id)
        ).all()

        events = [
            {
                "verified": event.verified,
                "party": event.party,
                "points": event.points,
            }
            for event in records
        ]

        return strategy_class().calculate_score(events)
