// Backend REST istemcisi. Adresler Vite proxy'si üzerinden backend'e gider.

async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, options)
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body?.detail
    let message = `İstek başarısız (${res.status})`
    if (detail && typeof detail === 'object' && !Array.isArray(detail) && detail.message) {
      message = detail.message // iş kuralı hatası: BID_TOO_LOW, BID_NOT_ALLOWED ...
    } else if (Array.isArray(detail)) {
      message = 'Geçersiz istek: tutar pozitif bir tam sayı olmalı.' // Pydantic doğrulaması
    }
    throw new Error(message)
  }
  return body
}

export const listAuctions = () => request('/auctions')

/**
 * Her teklif için benzersiz idempotency anahtarı.
 * crypto.randomUUID yalnızca güvenli bağlamda (HTTPS / localhost) vardır;
 * telefon yerel ağdan http://192.168.x.x ile bağlandığında yedek üretici kullanılır.
 */
export function newIdempotencyKey() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes) // güvenli olmayan bağlamda da kullanılabilir
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

export function placeBid(auctionId, userId, amount, idempotencyKey) {
  return request(`/auctions/${auctionId}/bids`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': String(userId),
      // Aynı tıklamanın tekrar gönderilmesi ikinci teklif açmaz (ADR-02).
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify({ amount }),
  })
}

export function setAutoBid(auctionId, userId, maxAmount) {
  return request(`/auctions/${auctionId}/auto-bid`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': String(userId) },
    body: JSON.stringify({ max_amount: maxAmount }),
  })
}

export function auctionSocketUrl(auctionId) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}/ws/auctions/${auctionId}`
}
