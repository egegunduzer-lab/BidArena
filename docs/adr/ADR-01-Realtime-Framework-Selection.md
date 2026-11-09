# ADR-01: Real-Time İletişim İçin FastAPI ve WebSocket Seçimi

## Durum (Context)
BidArena projesinde süreli açık artırma ihalelerinde verilen tekliflerin ve son dakika süre uzatmalarının tüm aktif kullanıcılara eşzamanlı ve düşük gecikmeyle (low latency) iletilmesi gerekmektedir.

## Karar (Decision)
Standard HTTP Polling yönteminin sunucuda yaratacağı aşırı yük ve gecikmeyi engellemek amacıyla, asenkron I/O mimarisini yerleşik olarak destekleyen **FastAPI** ve **WebSocket** protokolü tercih edilmiştir. Canlı yayın akışı için **Observer Design Pattern** uygulanacaktır.

## Sonuçlar (Consequences)
- Teklifler anında yayınlanır.
- Sunucu kaynak tüketimi minimize edilir.