from fastapi import APIRouter, HTTPException
from app.core.trust_strategy import BuyerTrustStrategy, SellerTrustStrategy

router = APIRouter()

@router.get("/api/users/{user_id}/trust")
def get_user_trust_score(user_id: int):
    # Gerçek projede veritabanından kullanıcı ve event'ler çekilir.
    # Örnek simülasyon:
    user_is_premium = False  # Ücretli üyelik kontrolü (Doküman Bölüm 6)
    if user_is_premium:
        return {"user_id": user_id, "trust_score": 0.0}

    user_role = "BUYER"  # veya "SELLER" (Kullanıcı rolüne göre)
    
    # Doğrulanmış (verified=True) örnek olaylar
    trust_events = [
        {"verified": True, "type": "GOOD_BEHAVIOR"},
        {"verified": False, "type": "CANCELED"}
    ]

    # Strategy Deseni Seçimi ve Puan Hesaplama
    strategy = BuyerTrustStrategy() if user_role == "BUYER" else SellerTrustStrategy()
    score = strategy.calculate_score(trust_events)
    return {"user_id": user_id, "trust_score": score}