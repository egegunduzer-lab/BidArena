"""API katmanının ortak bağımlılıkları."""
from fastapi import Header


def current_user_id(x_user_id: int = Header(..., description="Geçici: işlemi yapan kullanıcı")) -> int:
    """İşlemi yapan kullanıcı.

    Kimlik doğrulama modülü henüz yok; kullanıcı geçici olarak X-User-Id
    başlığıyla belirtilir. Auth eklendiğinde yalnızca bu fonksiyon değişir
    (ör. JWT'den kullanıcıyı okur); router'lar ve servisler değişmez.
    """
    return x_user_id
