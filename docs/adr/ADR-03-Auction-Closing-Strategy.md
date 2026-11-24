# ADR-03: Açık Artırma Kapanışı İçin Arka Plan Zamanlayıcısı ve Kilitli Yeniden Kontrol

## Durum (Context)
Doküman, açık artırmanın **sunucu saatine göre** kapanmasını ve kapanışta **tek bir koşullu kazanan** belirlenmesini istiyor. Aynı zamanda son iki dakikada gelen geçerli teklif süreyi uzatıyor (anti-sniping). Bu iki kural çakışabilir:

- Kapanış işlemi açık artırmayı "süresi dolmuş" olarak görür.
- Aynı anda, bitişten milisaniyeler önce gelen bir teklif kabul edilir ve süreyi uzatır.
- Kontrol edilmezse açık artırma hem kapanır hem de kapanıştan sonra kabul edilmiş bir teklif içerir; kazanan yanlış belirlenir.

Ek olarak kapanış, kimse sayfayı açmasa bile gerçekleşmeli ve tüm izleyicilere anında bildirilmelidir.

## Değerlendirilen Seçenekler
1. **İstek anında kapatma (lazy close):** Açık artırma ancak biri ona istek attığında kapatılır. Basit, ama kimse istek atmazsa kazanan belirlenmez ve bildirim gitmez. Reddedildi.
2. **Her açık artırma için ayrı zamanlayıcı (`asyncio.sleep(end_time - now)`):** Süre uzadıkça zamanlayıcının iptal edilip yeniden kurulması gerekir. Sunucu yeniden başlarsa zamanlayıcılar kaybolur. Reddedildi.
3. **Harici iş kuyruğu (Redis + Celery / RQ):** Dağıtık ortam için güçlü, ancak proje ölçeğinde ek altyapı ve işletim yükü getirir. Gerekirse ileride eklenebilir.
4. **Uygulama içinde periyodik tarayan tek bir arka plan görevi + veritabanı kilidi:** Seçildi.

## Karar (Decision)
- FastAPI `lifespan` ile açılışta tek bir asyncio görevi başlatılır (`app/core/scheduler.py`). Görev her `AUCTION_CLOSER_INTERVAL` saniyede (varsayılan 1 sn) `AuctionCloser.run_once()` çağırır.
- `run_once()` süresi dolmuş açık artırmaları veritabanı saatiyle (`clock_timestamp()`) bulur ve her birini **kendi kısa işleminde** kapatır (`app/services/auction_service.py`).
- Her kapanış iki önlem alır:
  1. Satır `SELECT ... FOR UPDATE SKIP LOCKED` ile kilitlenir. O anda bir teklif satırı kilitliyse kapanış **beklemez**, bu turu atlar ve bir sonraki turda yeniden dener. Böylece kapanış görevi teklif trafiği yüzünden tıkanmaz.
  2. Kilit alındıktan sonra bitiş zamanı **yeniden kontrol edilir**. Arada bir teklif süreyi uzatmışsa açık artırma kapatılmaz.
- Teklif motoru da (ADR-02) aynı satırı kilitler ve bitişi aynı veritabanı saatiyle kontrol eder. İki işlem aynı kilit üzerinden sıraya girdiği için "kapanıştan sonra kabul edilen teklif" oluşamaz.
- Kapanışta tek işlem içinde: durum `CLOSED` olur, kazanan (`highest_bid` sahibi) yazılır, otomatik teklif limitleri kapatılır, kazanan için `PROPOSED` durumunda buluşma randevusu açılır, kazanan / satıcı / kaybeden teklif sahipleri / takip edenler bildirim alır, `audit_logs` kaydı düşülür.
- Commit sonrası `AUCTION_CLOSED` olayı WebSocket odasına yayınlanır (ADR-01, Observer).

## Sonuçlar (Consequences)
- Kapanış, kullanıcı etkileşiminden bağımsız ve en fazla bir tur aralığı (≈1 sn) gecikmeyle gerçekleşir.
- Birden fazla sunucu süreci aynı anda kapanış çalıştırsa bile her açık artırma **bir kez** kapanır; kapanan satır `CLOSED` olduğu için tekrar seçilmez. (Test: `test_concurrent_closers_close_exactly_once`)
- Teklif satırı kilitliyken kapanış atlanır, süre uzamışsa kapatılmaz. (Test: `test_closer_skips_auction_locked_by_bid_and_respects_extension`; yeniden kontrol satırı kaldırıldığında bu test başarısız olur.)
- Sunucu yeniden başlarsa hiçbir durum kaybolmaz; zamanlayıcı ilk turda süresi geçmiş tüm açık artırmaları kapatır.
- Bedeli: her tur küçük bir sorgu çalıştırır (`auctions (status, end_time)` indeksi kullanılır). Çok sayıda sunucu ölçeğinde bu görev ayrı bir worker sürecine veya iş kuyruğuna (seçenek 3) taşınabilir; servis kodu (`AuctionCloser`) değişmeden kalır.
