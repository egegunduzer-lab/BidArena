# ADR-04: Prototip Kapsamı (Mobil İstemci, Kimlik Doğrulama, Paneller)

**Statü:** Kabul edildi (2026-11-26) · Mobil istemci PWA olarak güncellendi (2026-11-26)

## Durum (Context)
Proje dokümanı geniş bir hedef tanımlar: Flutter ile mobil alıcı uygulaması, React/Next.js ile satıcı ve yönetici web panelleri, kayıt/giriş ve üyelik yönetimi, teslimat, yedek alıcı, uyuşmazlık ve güven modülleri (bölüm 4, 7, 9). Ekip üç kişidir ve prototip sekiz haftalıktır. Dokümanın kendisi de "sekiz haftalık prototip kapsamında ödeme ve üyelik tahsilatı simüle edilecektir" der.

Değerlendirmenin temel başarı kriteri "eşzamanlı tekliflerde tutarlı sonuç üretirken güvenilir bir satış iş akışı kurmak"tır (bölüm 9). Bu yüzden sınırlı süre öncelikle bu kritere, yani teklif motoru, kapanış ve sunucu tarafı iş kurallarına ayrılmalıdır.

## Değerlendirilen Seçenekler
1. **Dokümandaki tüm istemcileri yüzeysel yapmak** (Flutter + iki web paneli + giriş): Her ekran var ama arkasındaki kurallar ve testler zayıf kalır. Eşzamanlılık kriteri gösterilemez. Reddedildi.
2. **Tek istemci, güçlü backend:** İstemci tarafı tek bir web uygulamasında toplanır; süre sunucu tarafı kurallara, eşzamanlılığa ve testlere ayrılır. Backend, istemciden bağımsız (REST + WebSocket) tasarlanır; diğer istemciler sonradan eklenebilir. **Seçildi.**

## Karar (Decision)

### 1. Mobil alıcı uygulaması: Flutter yerine PWA (React)
Doküman bölüm 9 "canlı teklif verebilen mobil alıcı uygulaması" bekler; bölüm 7'de Flutter **önerilir**. Mobil uygulama, mevcut React istemcisinin **Progressive Web App (PWA)** olarak telefona yüklenebilir hâle getirilmesiyle karşılanmıştır.

| Seçenek | Değerlendirme |
|---|---|
| Flutter | Yeni dil (Dart), ayrı kod tabanı, Flutter + Android SDK kurulumu. Kalan sürede canlı teklif ekranının iki kez yazılması gerekir. |
| React Native / Capacitor | Android SDK ve paketleme gerektirir; aynı ekran yine ikinci bir derleme hattıyla çalışır. |
| **PWA** | Tek kod tabanı; telefonda ana ekrana yüklenir, tam ekran (standalone) açılır; backend ve canlı akış aynı. **Seçildi.** |

Uygulama (`frontend_web/`):
- `public/manifest.webmanifest`: ad, `display: standalone`, tema rengi, 192/512 px ve maskable ikonlar; iOS için `apple-touch-icon` ve `apple-mobile-web-app-*` etiketleri.
- `public/sw.js`: yalnızca uygulama kabuğunu (HTML, derlenmiş JS/CSS, ikonlar) önbelleğe alır. `/api` ve `/ws` isteklerine **hiç dokunmaz**; fiyat ve teklifler her zaman sunucudan gelir, önbellekten eski fiyat gösterilmez.
- Telefon düzeni (600 px altı), dokunmatik hedefler, iOS'ta odaklanınca yakınlaştırmayı önleyen 16 px girişler; teklif geçildiğinde bildirim ve titreşim (`navigator.vibrate`).
- Telefon bilgisayara yerel ağdan `http://<bilgisayar-ip>` ile bağlandığında tarayıcı güvenli bağlam saymaz ve `crypto.randomUUID` yoktur; idempotency anahtarı bu durumda `crypto.getRandomValues` ile üretilir.

Sınırı: Tam "yükle" deneyimi ve service worker güvenli bağlam (HTTPS ya da `localhost`) ister. Yerel ağ üzerinden HTTP ile açıldığında uygulama mobil web olarak tam çalışır (canlı teklif, WebSocket, bildirim) ve ana ekrana kısayol olarak eklenebilir; service worker yalnızca HTTPS ile yayınlandığında devreye girer.

Backend hiçbir istemciye özel değildir: teklif REST ile (`POST /api/auctions/{id}/bids`), canlı akış WebSocket ile (`/ws/auctions/{id}`) yapılır (ADR-01). İleride bir Flutter uygulaması aynı uç noktaları kullanarak **backend değişmeden** eklenebilir.

### 2. Kimlik doğrulama: geçici `X-User-Id` başlığı
- Kayıt/giriş yoktur. İşlemi yapan kullanıcı `X-User-Id` başlığıyla belirtilir; demo ekranında seed kullanıcılarından biri seçilir.
- Bu bilgi **tek bir noktada** okunur: `backend/app/api/deps.py` içindeki `current_user_id`. Router'lar ve servisler kullanıcıyı yalnızca bu bağımlılıktan alır.
- Sonraki adım: parola özeti (`users.password_hash` sütunu hazır) ve JWT tabanlı giriş. Değişiklik `current_user_id`'nin token'dan kullanıcıyı okumasıyla sınırlı kalır; servis katmanı (Dependency Inversion) etkilenmez.
- **Güvenlik sınırı:** Bu yapı yalnızca prototip ve demo içindir; herkes başka bir kullanıcı adına istek atabilir. Üretimde kullanılamaz. WebSocket kanalı salt okumadır ve yalnızca fiyat, zaman ve kullanıcı numarası yayınlar (ad, e-posta, telefon gönderilmez).

### 3. Satıcı ve yönetici panelleri: prototipte yok
- Satıcı işlevlerinden **ilan açma ve kota** sunucu tarafında hazırdır (`POST /api/listings`, `GET /api/sellers/me/quota`) ve otomatik API dokümantasyonundan (`/docs`) kullanılabilir; arayüzü yoktur.
- Yönetici işlevleri (ilan denetimi, şikâyet ve kanıt inceleme, raporlar) prototip kapsamı dışındadır. İlgili tablolar (`disputes`, `evidence`, `trust_events`, `audit_logs`) şemada vardır; denetim kaydı teklif uzatma, kapanış ve ilan açmada zaten yazılmaktadır.

### 4. Ödeme ve üyelik tahsilatı: simülasyon
- Dokümanın izin verdiği şekilde gerçek tahsilat yoktur. Üyelik kayıtları `subscriptions.payment_ref` alanında simüle ödeme koduyla tutulur; kota kontrolü bu kayıtlara göre sunucuda yapılır.

### 5. Ek altyapı: Redis yok
- Teklif sıralaması ve kapanış PostgreSQL satır kilitleriyle çözülmüştür (ADR-02, ADR-03); WebSocket yayını tek süreç içindedir (ADR-01). Redis yalnızca çok süreçli ölçeklemede (yayın için Pub/Sub) gerekir.

## Prototipte Olanlar (Kapsam İçi)

| Doküman | Durum | Kanıt |
|---|---|---|
| 4-C Teklif motoru (WebSocket, minimum artış, sunucu saatiyle kapanış, anti-sniping, otomatik teklif, idempotency) | Tamam | `bid_service.py`, `test_bid_service.py`, `test_bid_concurrency.py` |
| Bölüm 9: canlı teklif verebilen mobil alıcı uygulaması | Tamam (PWA) | `manifest.webmanifest`, `sw.js`, `LiveAuction.jsx` |
| 4-D Koşullu kazanan ve randevu taslağı | Tamam | `auction_service.py`, `test_auction_close.py` |
| 4-A İlan kotasının sunucuda kontrolü | Tamam | `listing_service.py`, `test_listing_quota.py` |
| 4-B İlan açma, açık artırma listesi | Kısmen (filtre ve takip listesi yok) | `POST /api/listings`, `GET /api/auctions` |
| 4-G Yeni hesap teklif sınırı, gerekçeli geçici kısıt | Tamam | `BidPolicy`, `test_bid_service.py` |
| 4-H Teklif ve kapanış bildirimleri (kayıt) | Kısmen (okuma uç noktası yok) | `notifications` kayıtları |
| Bölüm 8: çift onay ve tek aktif yedek davet kuralları | Veritabanında tamam | `schema.sql`, `test_db_rules.py` |
| Bölüm 8: 100 eşzamanlı teklif, mükerrer istek, bitiş anı, otomatik limit | Tamam | `test_bid_concurrency.py` |

Senaryo 2 (randevu onayı, tek kullanımlık kod, iki taraflı teslim onayı) ve Senaryo 3 (yedek alıcı daveti) ayrı işlerde geliştirilmektedir (Issue #13, #14). Tamamlandıklarında bu tablo güncellenir.

## Sonuçlar (Consequences)
- Sunumda dokümanın temel başarı kriteri (eşzamanlılıkta tutarlılık) çalışan kod ve testlerle gösterilebilir.
- Backend'in istemciden bağımsız olması, Flutter ve panellerin sonradan eklenmesini backend değişikliği gerektirmeden mümkün kılar.
- Kimlik doğrulamanın tek noktada soyutlanması, giriş sistemi eklendiğinde değişikliği tek dosyayla sınırlar.
- Mobil alıcı deneyimi, ayrı bir kod tabanı açmadan telefonda gösterilebilir; web ve mobil aynı kodu ve aynı canlı akışı kullanır.
- Bedeli: yerel uygulama (Flutter) mağazadan dağıtılamaz; satıcı/yönetici panelleri ve giriş sistemi prototipte yoktur; demo seçilen demo kullanıcılarıyla yapılır.
