// Kimlik doğrulama modülü henüz yok. Demo için docs/seed.sql'deki kullanıcılar
// arasından seçim yapılır; seçilen kullanıcı X-User-Id başlığıyla gönderilir.
export const DEMO_USERS = [
  { id: 5, name: 'Mehmet Demir', note: 'alıcı' },
  { id: 6, name: 'Elif Şahin', note: 'alıcı' },
  { id: 7, name: 'Can Arslan', note: 'otomatik teklif limiti var' },
  { id: 8, name: 'Selin Aydın', note: 'alıcı' },
  { id: 4, name: 'Deniz Kaya', note: 'doğrulanmamış hesap' },
  { id: 9, name: 'Burak Çelik', note: 'geçici kısıtlı' },
  { id: 2, name: 'Ahmet Yılmaz', note: 'bisikletin satıcısı' },
]

export function userName(id) {
  if (id == null) return '-'
  return DEMO_USERS.find((u) => u.id === id)?.name ?? `Kullanıcı #${id}`
}
