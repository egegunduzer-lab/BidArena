# ADR-01: Gerçek Zamanlı İletişim İçin FastAPI ve WebSocket Seçimi

**Statü:** Kabul edildi (2026-11-09) · Uygulamaya göre güncellendi (2026-11-24)

## Durum (Context)
BidArena'da süreli açık artırmaya verilen her teklif, son dakika süre uzatmaları ve açık artırmanın kapanışı, o açık artırmayı izleyen tüm kullanıcılara **düşük gecikmeyle ve aynı anda** iletilmelidir (doküman 4-C: "WebSocket ile anlık teklif ve fiyat güncellemesi; teklif geçmişi ve geri sayım"). Ek gereksinimler:

- Geri sayım istemcinin saatine değil **sunucu saatine** dayanmalı.
- Yayın yalnızca veritabanına kesinleşmiş (commit edilmiş) teklifler için yapılmalı; reddedilen ya da geri alınan bir teklif ekrana düşmemeli.
- Backend, eşzamanlılık ve veritabanı işlemleri için Python ekosisteminde kalmalı (dersin önerdiği dil, ekibin ortak dili).

## Değerlendirilen Seçenekler

**İletim yöntemi**

| Seçenek | Artı | Eksi | Sonuç |
|---|---|---|---|
| HTTP polling (her N sn'de istek) | En basit | Gecikme = N sn; 100 izleyici × 1 sn = saniyede 100 boş istek | Reddedildi |
| Long polling | Gecikme düşük | Her olaydan sonra yeniden bağlanma; sunucuda bekleyen istek yönetimi karmaşık | Reddedildi |
| Server-Sent Events (SSE) | Tek yönlü yayın için yeterli, basit | Mobilde (Flutter) yerleşik destek zayıf; istemciden canlı tutma mesajı gönderilemez | Reddedildi |
| **WebSocket** | Çift yönlü, tek kalıcı bağlantı, düşük gecikme; Flutter ve tarayıcıda yerleşik destek | Bağlantı durumunu sunucu tutar | **Seçildi** |

**Framework**

| Seçenek | Değerlendirme |
|---|---|
| Django + Channels | WebSocket için ayrı ASGI katmanı ve kanal katmanı (genelde Redis) gerekir; prototip için ağır |
| Flask + Flask-SocketIO | Socket.IO protokolü standart WebSocket değildir, istemcide ek kütüphane ister |
| **FastAPI** | ASGI üzerine kurulu, WebSocket yerleşik; Pydantic ile girdi doğrulama ve otomatik OpenAPI dokümantasyonu (`/docs`) |

## Karar (Decision)
1. **FastAPI + yerleşik WebSocket** kullanılır. Canlı kanal: `GET /ws/auctions/{auction_id}` (`backend/app/api/realtime.py`).
2. **Observer deseni:** Her açık artırma bir "konu", ona bağlı WebSocket istemcileri "gözlemci"dir. `ConnectionManager` (`backend/app/core/websocket_manager.py`) odaları `auction_id → bağlantı kümesi` olarak tutar; `broadcast_to_auction` o odadaki herkese mesaj gönderir.
3. **Teklif REST ile verilir, WebSocket yalnızca yayın içindir.** Teklif `POST /api/auctions/{id}/bids` ile gelir. Böylece girdi doğrulama, idempotency anahtarı (`Idempotency-Key` başlığı) ve hata kodları (403/404/409/422) tek bir yerde kalır; aynı kurallar WebSocket üzerinden ikinci kez yazılmaz.
4. **Yayın commit'ten sonra yapılır.** API katmanı servisi çağırır, işlem commit edilince `NEW_BID` olayını yayınlar (`backend/app/api/bids.py`). Reddedilen ya da geri alınan teklif hiçbir zaman yayınlanmaz; mükerrer istek de yeniden yayınlanmaz.
5. **Bağlanınca anlık durum (SNAPSHOT):** İstemci bağlanır bağlanmaz güncel fiyat, minimum sonraki teklif, bitiş zamanı, **sunucu saati** ve son teklifler gönderilir. Geri sayım `end_time - server_time` farkından hesaplanır; istemcinin saati yanlış olsa da doğru kalır.
6. Olay türleri: `SNAPSHOT`, `NEW_BID` (otomatik karşı teklifler ve süre uzatma bilgisi dahil), `AUCTION_STARTED`, `AUCTION_CLOSED` (ADR-03), `PONG` (canlı tutma).
7. Yayın tüm bağlantılara **eşzamanlı** gönderilir (`asyncio.gather`); hata veren (kopmuş) bağlantı odadan çıkarılır, diğerleri etkilenmez.

## Sonuçlar (Consequences)
- Teklifler, kabul edildiği anda o açık artırmayı izleyen herkese tek bir mesajla ulaşır; istemci sürekli istek atmaz.
- REST + WebSocket ayrımı sayesinde teklif kuralları test edilebilir tek bir serviste toplanmıştır (`BidService`); WebSocket katmanı ince kalır.
- **Bilinen sınır:** Odalar Uvicorn sürecinin belleğinde tutulur. Tek süreçte doğru çalışır; birden fazla süreç veya sunucuya ölçeklenirse bir süreçte kabul edilen teklif diğer süreçteki izleyicilere ulaşmaz. Bu durumda yayın **Redis Pub/Sub** gibi ortak bir kanala taşınmalıdır. API katmanı yalnızca `manager.broadcast_to_auction` çağırdığı için bu değişiklik `ConnectionManager` ile sınırlı kalır.
- Kimlik doğrulama henüz yoktur; WebSocket kanalı herkese açık bir okuma kanalıdır. Yayında fiyat, zaman ve teklif verenlerin yalnızca kullanıcı numarası bulunur; ad, e-posta veya telefon gönderilmez.

## Doğrulama
`backend/tests/test_bid_api.py` ve `backend/tests/test_auction_close.py`:
- `test_websocket_receives_snapshot_then_new_bid`: bağlanınca SNAPSHOT, teklif sonrası NEW_BID (otomatik karşı teklif dahil) gelir.
- `test_websocket_ping`, `test_websocket_unknown_auction_is_closed`
- `test_scheduler_closes_auction_and_broadcasts`: kapanışta AUCTION_CLOSED yayınlanır.

Testler her push'ta GitHub Actions'ta çalışır (`.github/workflows/backend-tests.yml`).
