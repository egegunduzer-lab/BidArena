# BidArena - Gerçek Zamanlı Mobil Açık Artırma Platformu

BidArena, kullanıcıların ikinci el veya yeni eşyalarını gerçek zamanlı açık artırma usulüyle satabildiği ve alıcıların canlı olarak teklif verebildiği bir mobil uygulamadır.

##  Proje Hakkında

Bu proje, **Yazılım Tasarımı ve Mimarisi** dersi kapsamında geliştirilmiş olup, dağıtık sistem mimarisi, tasarım desenleri ve gerçek zamanlı haberleşme protokolleri üzerine odaklanmaktadır.

###  Geliştirme Ekibi ve Rol Dağılımı

*   **Ege Gündüzer:** Yazılım Mimarı (Software Architect & Backend Lead)
*   **Hüseyin Mataracı:** Yazılım Tasarımcısı (UI/UX Lead & Design Patterns)
*   **Yağız Ustabaşı:** Veri & Entegrasyon Sorumlusu (Database Architect)

##  Mimari ve Teknolojiler

Proje, yüksek performanslı ve eşzamanlı (concurrent) işlemleri destekleyen modern bir teknoloji yığını ile inşa edilmiştir:

*   **Backend Framework:** FastAPI (Python 3.12)
*   **Gerçek Zamanlı İletişim:** WebSockets (Observer Pattern)
*   **Veritabanı:** PostgreSQL
*   **ORM:** SQLAlchemy
*   **Mimari Desenler:** Observer Pattern, Strategy Pattern
*   **Eşzamanlılık Kontrolü:** Pessimistic Locking (`SELECT ... FOR UPDATE`)


##  Kurulum ve Çalıştırma (Yerel Geliştirme)

Projeyi yerel ortamınızda çalıştırmak için aşağıdaki adımları izleyin:

**1. Depoyu Klonlayın**
```bash
git clone [https://github.com/egegunduzer-lab/BidArena.git](https://github.com/egegunduzer-lab/BidArena.git)
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
**4. PostgreSQL Veritabanını Ayarlayın**
```bash
backend/app/core/database.py dosyasındaki bağlantı dizesini kendi yerel PostgreSQL bilgilerinize göre güncelleyin.
```
**5. Sunucuyu Başlatın**
```bash
uvicorn main:app --reload
```
## Mimari Kararlar
ADR-01: Gerçek zamanlı teklif iletimi için standart HTTP Polling yerine FastAPI WebSockets kullanılmasına karar verilmiştir.

ADR-02: Veritabanında eşzamanlı teklif çakışmalarını (Race Condition) önlemek için PostgreSQL seviyesinde Pessimistic Locking mekanizması uygulanmıştır.


