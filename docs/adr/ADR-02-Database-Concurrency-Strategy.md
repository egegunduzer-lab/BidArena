# ADR-02: Eşzamanlı Teklifler (Concurrency) İçin Veritabanı Kilit Stratejisi

**Statü:** Kabul edildi (2026-11-10) · Uygulamaya göre güncellendi (2026-11-24)

## Durum (Context)
Açık artırmanın son saniyelerinde çok sayıda alıcı aynı anda teklif verir. Bir teklifin kabul edilmesi tek bir yazma değil, **birbirine bağlı birkaç okuma ve yazmadır**:

1. Açık artırma aktif mi, sunucu saatine göre bitti mi?
2. Teklif, güncel fiyat + minimum artışa ulaşıyor mu? Teklif veren zaten önde mi?
3. Bu istek daha önce işlendi mi (idempotency)?
4. Teklifi kaydet, güncel fiyatı ve en yüksek teklifi güncelle.
5. Otomatik teklif limitleri varsa karşı teklifleri hesapla ve kaydet.
6. Son iki dakikadaysa süreyi uzat (anti-sniping), bildirim ve denetim kaydı bırak.

İki istek bu adımları aynı anda yürütürse ikisi de aynı "güncel fiyatı" görüp kabul edilebilir: aynı tutarda iki kazanan, düşen fiyat, kayıp güncelleme (lost update) veya aynı isteğin iki kez kaydı oluşur. Doküman bölüm 8 bunun test edilmesini açıkça ister: aynı anda 100 teklif, mükerrer teklif isteği, bitiş anı, otomatik teklif limiti.

## Değerlendirilen Seçenekler

| Seçenek | Değerlendirme | Sonuç |
|---|---|---|
| Kilit yok (uygulama içi kontrol) | Yukarıdaki yarış durumları oluşur. Testle kanıtlandı (aşağıda). | Reddedildi |
| Koşullu tek `UPDATE` (`... WHERE current_price + min_increment <= :amount`) | Sadece fiyat kuralı için yeterli; ancak idempotency, otomatik teklif döngüsü, süre uzatma ve bildirimler aynı tutarlı görüntüyü ister. Kurallar SQL'e dağılır. | Reddedildi |
| Optimistic locking (sürüm sütunu + yeniden deneme) | Çakışma seyrekse iyi. Açık artırmanın son saniyesinde çakışma **olağan durumdur**; isteklerin çoğu yeniden denemeye düşer, gecikme ve hata oranı artar. | Reddedildi |
| `SERIALIZABLE` izolasyon | Doğruluk sağlar ama çakışan işlemler serileştirme hatasıyla düşer; uygulamanın her işlemi yeniden deneme döngüsüne sarması gerekir. | Reddedildi |
| Redis dağıtık kilit | Ek altyapı; kilit ile veri farklı sistemlerde olduğu için kilit süresi dolarsa tutarsızlık riski. Tek PostgreSQL için gereksiz. | Reddedildi |
| **Pessimistic locking: `SELECT ... FOR UPDATE`** | Aynı açık artırmaya gelen teklifler veritabanında sıraya girer; tüm kurallar tek işlemde, tutarlı veriyle çalışır. | **Seçildi** |

## Karar (Decision)
`BidService` (`backend/app/services/bid_service.py`) her teklifi ve otomatik teklif limiti değişikliğini **tek bir veritabanı işlemi** içinde şu sırayla işler:

1. **Kilit:** Açık artırma satırı `with_for_update()` ile kilitlenir (SQL: `SELECT ... FROM auctions WHERE id = :id FOR UPDATE`). Aynı açık artırmaya gelen diğer işlemler bu noktada bekler; **farklı açık artırmalar birbirini beklemez.**
2. **Sunucu saati:** Saat, kilit alındıktan sonra veritabanından `clock_timestamp()` ile okunur. (`now()` işlemin başladığı anı verir ve kilit beklerken geçen süreyi saymaz.) Uygulama sunucusunun veya istemcinin saati kullanılmaz.
3. **Idempotency kontrolü kilitten sonra yapılır.** Aynı `(bidder_id, idempotency_key)` ile gelen iki kopya da kilitte sıraya girer; ikincisi birincinin commit edilmiş kaydını görür ve yeni kayıt açmadan ilk sonucu döner. Anahtar farklı bir teklif için yeniden kullanılırsa `409 IDEMPOTENCY_CONFLICT` döner.
4. Kural kontrolleri, teklif kaydı, otomatik teklif çözümü, süre uzatma, bildirim ve denetim kaydı aynı işlemde yapılır; **commit kilidi bırakır.** Herhangi bir hata olursa işlem geri alınır, kilit yine bırakılır.
5. WebSocket yayını commit'ten **sonra** yapılır (ADR-01).

**Veritabanı seviyesindeki son savunma hattı** (`docs/schema.sql`): `bids (bidder_id, idempotency_key)` tekil index'i, `CHECK (current_price >= start_price)`, `auto_bid_limits (auction_id, user_id)` tekilliği. Uygulama kodunda bir hata olsa bile mükerrer kayıt veritabanına giremez.

## Sonuçlar (Consequences)
- **Tek kazanan, tutarlı fiyat:** Kabul edilen teklifler işlenme sırasına göre kesin artandır; güncel fiyat her zaman en son kabul edilen teklife eşittir.
- **Deadlock riski yok:** Her işlem yalnızca **bir** açık artırma satırını kilitler. Kilitlenen kaynak sırası sabit olduğundan karşılıklı bekleme oluşmaz.
- **Bedeli:** Aynı açık artırmaya gelen teklifler sırayla işlenir. Kilit süresi tek bir işlem kadardır (birkaç milisaniye). Otomatik teklif döngüsü kilidi tutarken çalışır; bu döngü 50 turla sınırlandırılmıştır (her turda fiyat kesin arttığı için döngü sonlanır; testlerdeki senaryolarda 1–2 tur sürer). Proje ölçeği için kabul edilebilir.
- **Kapanışla etkileşim:** Kapanış görevi aynı satırı `FOR UPDATE SKIP LOCKED` ile kilitler; teklif işlenirken beklemez, sonraki turda dener ve bitişi kilitten sonra yeniden kontrol eder (ADR-03).
- Redis bazlı dağıtık kilide gerek kalmaz; tek doğruluk kaynağı PostgreSQL'dir.
- **Aynı yaklaşım ilan kotasında da kullanılır:** `ListingService` ilan açarken satıcının aktif üyelik satırını `FOR UPDATE` ile kilitler, sayım ve kayıt aynı işlemde yapılır. Kotanın son hakkı için aynı anda gelen 10 istekten yalnızca biri kabul edilir (`test_concurrent_requests_cannot_exceed_quota`; kilit kaldırılınca bu test başarısız olur).

## Doğrulama
`backend/tests/test_bid_concurrency.py`: her teklif ayrı thread ve ayrı veritabanı bağlantısıyla gönderilir, bir `Barrier` hepsini aynı anda serbest bırakır.

| Test | Senaryo | Beklenen ve gözlenen sonuç |
|---|---|---|
| `test_100_concurrent_bids_with_different_amounts_stay_consistent` | 100 kullanıcı, 100 farklı tutar, karışık sırada | Kabul edilenler kesin artan, aralarında en az minimum artış var; güncel fiyat = en yüksek tutar |
| `test_100_concurrent_bids_with_same_amount_accept_exactly_one` | 100 kullanıcı, aynı tutar | Tam olarak 1 kabul, 99 `BID_TOO_LOW` |
| `test_duplicate_requests_sent_concurrently_create_one_bid` | Aynı istek (aynı anahtar) 30 kez aynı anda | Tek kayıt; 29 yanıt "mükerrer" olarak ilk sonucu döner |
| `test_concurrent_bids_against_auto_bidder_respect_limit` | Otomatik limit açıkken 100 eşzamanlı teklif | Otomatik teklifler hiçbir zaman limiti aşmaz |

**Kilidin gerekliliğinin kanıtı:** `with_for_update()` geçici olarak kaldırılıp aynı testler çalıştırıldığında **4 testin 4'ü de başarısız** olmuştur; kilit geri konunca hepsi geçer. Yani testler kilidi gerçekten doğrulamaktadır.

İş kuralı testleri (`test_bid_service.py`): bitiş anında teklif reddi, son iki dakikada süre uzatma, yeniden deneme ile mükerrer kayıt oluşmaması, otomatik teklif limitleri. Tüm testler her push'ta GitHub Actions'ta gerçek PostgreSQL 17 ile çalışır.
