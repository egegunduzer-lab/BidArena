-- BidArena örnek veri (seed)
-- schema.sql yüklendikten sonra çalıştırın:  psql -d bidarena -f seed.sql
-- Dosya tekrar çalıştırılabilir: önce tüm tabloları boşaltır, sonra yeniden doldurur.
-- Tarihler now()'a göre ayarlıdır; açık artırmalar her çalıştırmada "canlı" kalır.
--
-- NOT: password_hash alanları yer tutucudur. Gerçek giriş için backend kendi
-- hash fonksiyonuyla (örn. bcrypt) şifre üretmelidir.
--
-- Gösterilen senaryolar (proje dokümanı, bölüm 5):
--   Senaryo 1  Canlı açık artırma       -> auction 1 (ACTIVE, teklifler, otomatik teklif, uzatma)
--   Senaryo 2  Elden teslim             -> auction 3 + appointment 2 (çift onay, COMPLETED)
--   Senaryo 3  Satış gerçekleşmezse     -> auction 2 + appointment 1 (NO_SHOW, yedek alıcı daveti)
--   Senaryo 4  Ürün uyuşmazlığı         -> auction 5 + appointment 3 (DISPUTED, kanıt, yönetici incelemesi)

BEGIN;

TRUNCATE users, subscriptions, listings, watchlist, auctions, bids, auto_bid_limits,
         appointments, delivery_confirmations, disputes, evidence, trust_events,
         backup_offers, notifications, audit_logs
         RESTART IDENTITY CASCADE;

-- ---------------------------------------------------------------- Kullanıcılar
INSERT INTO users (id, email, password_hash, full_name, phone, role, is_verified,
                   restricted_until, restriction_reason, created_at) VALUES
 (1, 'admin@bidarena.example',  'DEMO_HASH', 'Platform Yöneticisi', NULL,            'ADMIN', true,  NULL, NULL, now() - interval '200 days'),
 (2, 'ahmet@example.com',       'DEMO_HASH', 'Ahmet Yılmaz',        '05550000002',   'USER',  true,  NULL, NULL, now() - interval '150 days'),  -- bireysel satıcı
 (3, 'teknomagaza@example.com', 'DEMO_HASH', 'Tekno Mağaza',        '05550000003',   'USER',  true,  NULL, NULL, now() - interval '300 days'),  -- profesyonel satıcı
 (4, 'yeni@example.com',        'DEMO_HASH', 'Deniz Kaya',          NULL,            'USER',  false, NULL, NULL, now() - interval '1 day'),     -- yeni hesap (teklif sınırı)
 (5, 'mehmet@example.com',      'DEMO_HASH', 'Mehmet Demir',        '05550000005',   'USER',  true,  NULL, NULL, now() - interval '90 days'),   -- buluşmaya gelmeyen kazanan
 (6, 'elif@example.com',        'DEMO_HASH', 'Elif Şahin',          '05550000006',   'USER',  true,  NULL, NULL, now() - interval '120 days'),
 (7, 'can@example.com',         'DEMO_HASH', 'Can Arslan',          '05550000007',   'USER',  true,  NULL, NULL, now() - interval '60 days'),   -- otomatik teklif kullanıcısı
 (8, 'selin@example.com',       'DEMO_HASH', 'Selin Aydın',         '05550000008',   'USER',  true,  NULL, NULL, now() - interval '200 days'),
 (9, 'burak@example.com',       'DEMO_HASH', 'Burak Çelik',         '05550000009',   'USER',  true,
     now() + interval '7 days', 'Tekrarlanan sahte teklif şikayetleri', now() - interval '45 days');                                       -- geçici kısıtlı

-- ---------------------------------------------------------------- Üyelikler (simüle ödeme)
INSERT INTO subscriptions (id, user_id, plan, listing_quota, price_tl, status, starts_at, ends_at, payment_ref) VALUES
 (1, 2, 'INDIVIDUAL',   20,  599, 'ACTIVE',  now() - interval '150 days', now() + interval '215 days', 'SIM-2026-0001'),
 (2, 3, 'PROFESSIONAL', 200, 1999, 'ACTIVE', now() - interval '300 days', now() + interval '65 days',  'SIM-2026-0002'),
 (3, 6, 'INDIVIDUAL',   20,  599, 'EXPIRED', now() - interval '500 days', now() - interval '135 days', 'SIM-2025-0107');

-- ---------------------------------------------------------------- İlanlar
INSERT INTO listings (id, seller_id, subscription_id, title, description, defects, category, city, district,
                      photos, safe_meeting_prefs, status, created_at) VALUES
 (1, 2, 1, 'Trek Marlin 7 Dağ Bisikleti', '2023 model, 29 jant, L kadro.', 'Sağ vites kolunda çizik.',
     'Spor', 'İstanbul', 'Kadıköy', '["https://example.com/p/1a.jpg","https://example.com/p/1b.jpg"]',
     '{"public_place": true, "preferred": "Kadıköy Belediyesi önü"}', 'ACTIVE', now() - interval '3 days'),
 (2, 2, 1, 'Sony WH-1000XM5 Kulaklık', 'Kutulu, faturalı.', 'Kulak yastığında hafif aşınma.',
     'Elektronik', 'İstanbul', 'Üsküdar', '["https://example.com/p/2a.jpg"]',
     '{"public_place": true, "preferred": "AVM girişi"}', 'CLOSED', now() - interval '10 days'),
 (3, 3, 2, 'MacBook Air M2 13"', '8GB/256GB, pil sağlığı %92.', 'Kusur yok.',
     'Elektronik', 'Ankara', 'Çankaya', '["https://example.com/p/3a.jpg","https://example.com/p/3b.jpg"]',
     '{"public_place": true, "preferred": "Mağaza"}', 'CLOSED', now() - interval '14 days'),
 (4, 3, 2, 'iPhone 14 128GB', 'Garantisi devam ediyor.', 'Ekranda koruyucu altında ince çizik.',
     'Elektronik', 'Ankara', 'Çankaya', '["https://example.com/p/4a.jpg"]',
     '{"public_place": true, "preferred": "Mağaza"}', 'ACTIVE', now() - interval '1 day'),
 (5, 2, 1, 'Ahşap Çalışma Masası', '120x60 cm.', 'Bir ayağında boya kalkması.',
     'Ev & Yaşam', 'İstanbul', 'Kadıköy', '[]',
     '{"public_place": false}', 'DRAFT', now() - interval '2 hours'),
 (6, 2, 1, 'Canon EOS 250D Fotoğraf Makinesi', '18-55 lens ile.', 'Kusur yok.',
     'Elektronik', 'İstanbul', 'Beşiktaş', '["https://example.com/p/6a.jpg"]',
     '{"public_place": true, "preferred": "Metro çıkışı"}', 'CLOSED', now() - interval '12 days');

-- ---------------------------------------------------------------- Takip listesi
-- Kullanıcı 4 ilan 2'yi sadece takip ediyor; teklif vermediği için yedek alıcı listesinde yok (doküman F).
INSERT INTO watchlist (user_id, listing_id, created_at) VALUES
 (4, 1, now() - interval '1 day'), (6, 1, now() - interval '2 days'),
 (8, 4, now() - interval '5 hours'), (4, 2, now() - interval '9 days');

-- ---------------------------------------------------------------- Açık artırmalar
-- highest_bid_id foreign key'i DEFERRED olduğundan teklifler aynı işlemde sonradan eklenebilir.
INSERT INTO auctions (id, listing_id, start_price, min_increment, current_price, highest_bid_id,
                      start_time, end_time, extension_count, status, winner_id) VALUES
 (1, 1, 10000, 250, 11500, 4,  now() - interval '3 days',  now() + interval '6 hours', 1, 'ACTIVE',    NULL), -- Senaryo 1
 (2, 2,  5000, 100,  5600, 7,  now() - interval '10 days', now() - interval '6 days',  0, 'CLOSED',    5),    -- Senaryo 3
 (3, 3, 20000, 500, 21000, 9,  now() - interval '14 days', now() - interval '9 days',  2, 'CLOSED',    8),    -- Senaryo 2
 (4, 4, 30000, 500, 30000, NULL, now() + interval '1 day', now() + interval '4 days',  0, 'SCHEDULED', NULL),
 (5, 6,  8000, 200,  8600, 11, now() - interval '12 days', now() - interval '8 days',  0, 'CLOSED',    6);    -- Senaryo 4

-- ---------------------------------------------------------------- Teklifler
INSERT INTO bids (id, auction_id, bidder_id, amount, is_auto, idempotency_key, created_at) VALUES
 -- auction 1 (canlı)
 (1, 1, 5, 10250, false, 'a1-u5-001', now() - interval '2 days'),
 (2, 1, 6, 10500, false, 'a1-u6-001', now() - interval '1 day'),
 (3, 1, 5, 11000, false, 'a1-u5-002', now() - interval '20 hours'),
 (4, 1, 7, 11500, true,  'a1-u7-auto-001', now() - interval '20 hours' + interval '1 second'), -- otomatik karşı teklif
 -- auction 2 (kazanan gelmedi)
 (5, 2, 6, 5100, false, 'a2-u6-001', now() - interval '8 days'),
 (6, 2, 7, 5300, false, 'a2-u7-001', now() - interval '7 days'),
 (7, 2, 5, 5600, false, 'a2-u5-001', now() - interval '6 days' - interval '1 minute'),
 -- auction 3 (tamamlanan satış; son dakika teklifleri süreyi 2 kez uzattı)
 (8, 3, 6, 20500, false, 'a3-u6-001', now() - interval '9 days' - interval '3 minutes'),
 (9, 3, 8, 21000, false, 'a3-u8-001', now() - interval '9 days' - interval '1 minute'),
 -- auction 5 (ürün uyuşmazlığı)
 (10, 5, 8, 8200, false, 'a5-u8-001', now() - interval '10 days'),
 (11, 5, 6, 8600, false, 'a5-u6-001', now() - interval '9 days');

-- ---------------------------------------------------------------- Otomatik teklif limitleri
INSERT INTO auto_bid_limits (id, auction_id, user_id, max_amount, is_active, created_at) VALUES
 (1, 1, 7, 13000, true, now() - interval '21 hours');

-- ---------------------------------------------------------------- Buluşma randevuları
INSERT INTO appointments (id, auction_id, buyer_id, seller_id, agreed_price, location, meeting_time,
                          buyer_accepted, seller_accepted, otp_hash, otp_expires_at, otp_used_at,
                          otp_failed_attempts, status, created_at) VALUES
 -- Senaryo 3: kazanan (5) buluşmaya gelmedi
 (1, 2, 5, 2, 5600, 'Üsküdar Capitol AVM girişi', now() - interval '5 days', true, true,
     'DEMO_OTP_HASH', now() - interval '5 days' + interval '2 hours', NULL, 0, 'NO_SHOW_BUYER', now() - interval '6 days'),
 -- Senaryo 2: başta CONFIRMED; iki onaydan sonra COMPLETED'a çekilecek
 (2, 3, 8, 3, 21000, 'Tekno Mağaza, Çankaya', now() - interval '8 days', true, true,
     'DEMO_OTP_HASH', now() - interval '8 days' + interval '2 hours', now() - interval '8 days', 0, 'CONFIRMED', now() - interval '9 days'),
 -- Senaryo 4: ürün ilandan farklı çıktı
 (3, 5, 6, 2, 8600, 'Beşiktaş metro çıkışı', now() - interval '7 days', true, true,
     'DEMO_OTP_HASH', now() - interval '7 days' + interval '2 hours', now() - interval '7 days', 1, 'DISPUTED', now() - interval '8 days');

-- ---------------------------------------------------------------- Teslimat onayları (çift onay)
INSERT INTO delivery_confirmations (id, appointment_id, user_id, party, confirmed_at) VALUES
 (1, 2, 8, 'BUYER',  now() - interval '8 days'),
 (2, 2, 3, 'SELLER', now() - interval '8 days');
UPDATE appointments SET status = 'COMPLETED' WHERE id = 2;   -- trigger iki onayı kontrol eder

-- ---------------------------------------------------------------- Uyuşmazlıklar ve kanıtlar
INSERT INTO disputes (id, appointment_id, opened_by, against_user_id, type, description, status,
                      resolution_note, resolved_by, appeal_note, created_at, resolved_at) VALUES
 -- Tek taraflı şikayet: otomatik ceza yok, yönetici incelemesinde (doküman G)
 (1, 1, 2, 5, 'NO_SHOW', 'Alıcı randevu saatinde gelmedi, telefona yanıt vermedi.', 'UNDER_REVIEW',
     NULL, NULL, NULL, now() - interval '5 days', NULL),
 (2, 3, 6, 2, 'ITEM_MISMATCH', 'Lens ilanda belirtilenden farklı, ön camda çizik var.', 'OPEN',
     NULL, NULL, NULL, now() - interval '7 days', NULL);

INSERT INTO evidence (id, dispute_id, uploaded_by, file_url, note, created_at) VALUES
 (1, 1, 2, 'https://example.com/e/1-mesajlasma.png', 'Randevu onay mesajları', now() - interval '5 days'),
 (2, 2, 6, 'https://example.com/e/2-lens.jpg',       'Lensteki çizik',         now() - interval '7 days'),
 (3, 2, 2, 'https://example.com/e/3-ilan-foto.jpg',  'Satış öncesi fotoğraf',  now() - interval '6 days');

-- ---------------------------------------------------------------- Güven olayları
-- Sadece doğrulanmış olaylar puanı etkiler; ücretli üyelik puan vermez.
INSERT INTO trust_events (id, user_id, party, type, points, verified, appointment_id, dispute_id, created_at) VALUES
 (1, 8, 'BUYER',  'SALE_COMPLETED', 10, true,  2, NULL, now() - interval '8 days'),
 (2, 3, 'SELLER', 'SALE_COMPLETED', 10, true,  2, NULL, now() - interval '8 days'),
 (3, 5, 'BUYER',  'NO_SHOW',       -20, false, 1, 1,    now() - interval '5 days');  -- inceleme sürüyor, henüz doğrulanmadı

-- ---------------------------------------------------------------- Yedek alıcı davetleri (Senaryo 3)
-- 2. sıradaki (7) reddetti, 3. sıradakine (6) kendi teklif fiyatından davet gitti. Aynı anda tek PENDING.
INSERT INTO backup_offers (id, auction_id, user_id, bid_id, price, rank, status, expires_at, created_at, responded_at) VALUES
 (1, 2, 7, 6, 5300, 1, 'REJECTED', now() - interval '3 days', now() - interval '4 days', now() - interval '3 days' - interval '6 hours'),
 (2, 2, 6, 5, 5100, 2, 'PENDING',  now() + interval '1 day',  now() - interval '1 day',  NULL);

-- ---------------------------------------------------------------- Bildirimler
INSERT INTO notifications (id, user_id, type, payload, is_read, created_at) VALUES
 (1, 5, 'OUTBID',       '{"auction_id": 1, "new_price": 11500}',                  false, now() - interval '20 hours'),
 (2, 6, 'OUTBID',       '{"auction_id": 1, "new_price": 11000}',                  true,  now() - interval '20 hours'),
 (3, 8, 'AUCTION_WON',  '{"auction_id": 3, "price": 21000}',                      true,  now() - interval '9 days'),
 (4, 6, 'BACKUP_OFFER', '{"auction_id": 2, "price": 5100, "backup_offer_id": 2}', false, now() - interval '1 day'),
 (5, 2, 'DISPUTE_OPENED','{"dispute_id": 2, "appointment_id": 3}',                false, now() - interval '7 days'),
 (6, 8, 'AUCTION_STARTING','{"auction_id": 4, "listing_id": 4}',                  false, now() - interval '5 hours');

-- ---------------------------------------------------------------- Denetim kayıtları
INSERT INTO audit_logs (id, actor_id, action, entity, entity_id, data, created_at) VALUES
 (1, NULL, 'AUCTION_CLOSED',     'auction',     3, '{"winner_id": 8, "price": 21000}', now() - interval '9 days'),
 (2, 1,    'USER_RESTRICTED',    'user',        9, '{"days": 7}',                        now() - interval '1 day'),
 (3, 2,    'BACKUP_OFFER_SENT',  'backup_offer',2, '{"rank": 2}',                       now() - interval '1 day'),
 (4, NULL, 'AUCTION_EXTENDED',   'auction',     1, '{"extension_sec": 120}',             now() - interval '20 hours');

-- ---------------------------------------------------------------- ID sayaçlarını güncelle
-- Elle id verdiğimiz için sonraki kayıtlar çakışmasın diye sayaçları ilerletiyoruz.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['users','subscriptions','listings','auctions','bids','auto_bid_limits',
                           'appointments','delivery_confirmations','disputes','evidence',
                           'trust_events','backup_offers','notifications','audit_logs'] LOOP
    EXECUTE format('SELECT setval(pg_get_serial_sequence(%L, ''id''), COALESCE((SELECT max(id) FROM %I), 1))', t, t);
  END LOOP;
END $$;

COMMIT;
