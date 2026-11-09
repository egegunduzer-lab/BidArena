from fastapi import FastAPI

app = FastAPI(
    title="BidArena API",
    description="Gerçek Zamanlı Mobil Açık Artırma Platformu API Servisleri",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": "BidArena Engine",
        "message": "Backend servisi başarıyla çalışıyor."
    }