# ADR-02: Eşzamanlı Teklifler (Concurrency) İçin Veritabanı Kilit Stratejisi

## Durum (Context)
Açık artırmanın son saniyelerinde birden fazla alıcının aynı anda teklif vermesi durumunda, veritabanına gelen eşzamanlı isteklerin birbirini ezmesi (Race Condition) ve tutarsız güncel fiyat (current_price) oluşması riski bulunmaktadır.

## Karar (Decision)
Tutarlılığı garanti altına almak (ACID) amacıyla PostgreSQL seviyesinde **Pessimistic Locking** uygulanmasına karar verilmiştir. SQLAlchemy üzerinden `with_for_update()` metodu kullanılarak (SQL karşılığı: `SELECT ... FOR UPDATE`), bir teklif işlenirken ilgili açık artırma satırı diğer işlemlere karşı kilitlenecektir.

## Sonuçlar (Consequences)
- Veri bütünlüğü %100 garanti altına alınır (Tek bir kazanan olur).
- Sistemde Redis bazlı karmaşık bir Distributed Lock kullanılmasına gerek kalmaz.
- Çok yoğun isteklerde kilit bekleme (lock wait) süresi milisaniyelik artışlar gösterebilir, ancak proje ölçeği için kabul edilebilirdir.