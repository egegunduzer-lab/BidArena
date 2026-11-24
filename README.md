# BidArena - Gerçek Zamanlı Mobil Açık Artırma Platformu

[![Backend Tests](https://github.com/egegunduzer-lab/BidArena/actions/workflows/backend-tests.yml/badge.svg)](https://github.com/egegunduzer-lab/BidArena/actions/workflows/backend-tests.yml)

BidArena, kullanıcıların ikinci el veya yeni eşyalarını gerçek zamanlı açık artırma usulüyle satabildiği ve alıcıların canlı olarak teklif verebildiği bir mobil uygulamadır.

##  Proje Hakkında

Bu proje, **Yazılım Tasarımı ve Mimarisi** dersi kapsamında geliştirilmiş olup, dağıtık sistem mimarisi, tasarım desenleri ve gerçek zamanlı haberleşme protokolleri üzerine odaklanmaktadır.

###  Geliştirme Ekibi ve Rol Dağılımı

*   **Ege Gündüzer:** Yazılım Mimarı (Software Architect & Backend Lead)
*   **Hüseyin Mataracı:** Yazılım Tasarımcısı (UI/UX Lead & Design Patterns)
*   **Yağız Ustabaşı:** Veri & Entegrasyon Sorumlusu (Database Architect)

##  Mimari ve Teknolojiler

Proje, yüksek performanslı ve eşzamanlı (concurrent) işlemleri destekleyen modern bir teknoloji yığını ile inşa edilmiştir:

*   **Backend Framework:** FastAPI (Python 3.12+, 3.14 ile test edildi)
*   **Gerçek Zamanlı İletişim:** WebSockets (Observer Pattern)
*   **Veritabanı:** PostgreSQL
*   **ORM:** SQLAlchemy
*   **Mimari Desenler:** Observer Pattern, Strategy Pattern
*   **Eşzamanlılık Kontrolü:** Pessimistic Locking (`SELECT ... FOR UPDATE`)


##  Kurulum ve Çalıştırma (Yerel Geliştirme)

Projeyi yerel ortamınızda çalıştırmak için aşağıdaki adımları izleyin:

**1. Depoyu Klonlayın**
```bash
git clone https://github.com/egegunduzer-lab/BidArena.git
cd BidArena/backend
```
**2. Sanal Ortam Oluşturun ve Aktif Edin**
```bash
python -m venv venv
# Windows için:
venv\Scripts\activate
# macOS/Linux için:
source venv/bin/activate
```
**3. Gerekli Kütüphaneleri Ekleyin**
```bash
pip install -r requirements.txt
```
**4. PostgreSQL Veritabanını Kurun**

Veritabanını oluşturup şemayı ve örnek veriyi yükleyin (proje ana klasöründen):
```bash
createdb bidarena
psql -d bidarena -f docs/schema.sql
psql -d bidarena -f docs/seed.sql
```
`seed.sql` tekrar çalıştırılabilir; tabloları boşaltıp örnek veriyi yeniden yükler. Örnek veri, proje dokümanındaki 4 senaryonun (canlı açık artırma, elden teslim, satış gerçekleşmezse yedek alıcı, ürün uyuşmazlığı) hepsini içerir.

Backend varsayılan olarak `postgresql+psycopg2://localhost:5432/bidarena` adresine bağlanır (Postgres.app için ek ayar gerekmez). Kullanıcı adı/şifre gerekiyorsa `DATABASE_URL` ortam değişkenini ayarlayın:
```bash
export DATABASE_URL="postgresql+psycopg2://kullanici:sifre@localhost:5432/bidarena"
```
Bağlantıyı ve modellerin şemayla uyumunu kontrol etmek için (`backend` klasöründe):
```bash
python check_db.py
```
Sonuç satırında "Her şey yolunda" görünmelidir.

> Not: Tabloların tek kaynağı `docs/schema.sql` dosyasıdır. Şema değişirse `backend/app/models.py` de güncellenmeli; `check_db.py` aradaki farkı gösterir.
**5. Sunucuyu Başlatın**
```bash
uvicorn main:app --reload
```
API dokümantasyonu: http://localhost:8000/docs

Sunucu açıkken arka planda her saniye süresi dolan açık artırmaları kapatan bir görev çalışır (ADR-03). Aralığı `AUCTION_CLOSER_INTERVAL` (saniye) ile değiştirilebilir, `AUCTION_CLOSER_ENABLED=0` ile kapatılabilir.

**6. Testleri Çalıştırın**

Testler her seferinde `docs/seed.sql` ile veritabanını sıfırlar; bu yüzden **ayrı bir test veritabanı** kullanın:
```bash
createdb bidarena_test
psql -d bidarena_test -f docs/schema.sql
cd backend
pip install -r requirements-dev.txt
TEST_DATABASE_URL="postgresql+psycopg2://localhost:5432/bidarena_test" pytest
```
Windows PowerShell'de: `$env:TEST_DATABASE_URL="postgresql+psycopg2://localhost:5432/bidarena_test"; pytest`

**Sürekli Entegrasyon (CI):** `main`'e her push'ta ve her pull request'te GitHub Actions ([backend-tests.yml](.github/workflows/backend-tests.yml)) PostgreSQL 17 açar, şemayı ve örnek veriyi yükler, `check_db.py` ile model/şema uyumunu doğrular ve tüm testleri çalıştırır. Sonuçlar [Actions](https://github.com/egegunduzer-lab/BidArena/actions) sekmesinde görülür; JUnit raporu her çalıştırmada artifact olarak indirilebilir.

## Mimari Diyagramlar
- [Bileşen diyagramı](docs/design/component-diagram.png) ([kaynak](docs/design/component-diagram.plantuml)): API, servis, çekirdek ve veri erişim katmanları
- [Dağıtım diyagramı](docs/design/deployment-diagram.png) ([kaynak](docs/design/deployment-diagram.plantuml)): istemci, Uvicorn süreci, PostgreSQL ve CI

PNG'ler PlantUML kaynaklarından üretilir: `java -jar plantuml.jar -tpng -charset UTF-8 docs/design/*.plantuml`

## Mimari Kararlar
ADR-01: Gerçek zamanlı teklif iletimi için standart HTTP Polling yerine FastAPI WebSockets kullanılmasına karar verilmiştir.

ADR-02: Veritabanında eşzamanlı teklif çakışmalarını (Race Condition) önlemek için PostgreSQL seviyesinde Pessimistic Locking mekanizması uygulanmıştır.

ADR-03: Açık artırma kapanışı, uygulama içinde periyodik çalışan bir arka plan göreviyle yapılır; satır `FOR UPDATE SKIP LOCKED` ile kilitlenir ve bitiş zamanı kilit alındıktan sonra yeniden kontrol edilir.


