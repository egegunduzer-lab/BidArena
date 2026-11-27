from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.trust_service import TrustScoreService

router = APIRouter()


@router.get("/api/users/{user_id}/trust")
def get_user_trust_score(
    user_id: int,
    party: Literal["BUYER", "SELLER"] = "BUYER",
    db: Session = Depends(get_db),
):
    score = TrustScoreService(db).calculate_score(user_id, party)
    return {"user_id": user_id, "trust_score": score}
