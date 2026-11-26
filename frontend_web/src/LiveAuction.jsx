import { useState } from 'react'
import { newIdempotencyKey, placeBid, setAutoBid } from './api'
import BidHistory from './BidHistory'
import Countdown from './Countdown'
import { userName } from './demoUsers'
import { useAuctionFeed } from './useAuctionFeed'

const tl = (n) => `${n.toLocaleString('tr-TR')} ₺`

export default function LiveAuction({ auctionId, userId }) {
  const { auction, connected, notice, serverNow } = useAuctionFeed(auctionId, userId)
  const [amount, setAmount] = useState('')
  const [maxAmount, setMaxAmount] = useState('')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState(null)

  if (!auction) {
    return <div className="card loading">{connected ? 'Yükleniyor…' : 'Sunucuya bağlanılıyor…'}</div>
  }

  const isClosed = auction.status === 'CLOSED'
  const isSeller = auction.listing.seller_id === userId
  const isLeader = auction.highest_bidder_id === userId

  async function submitBid(e) {
    e.preventDefault()
    const value = amount === '' ? auction.min_next_bid : Number(amount)
    setPending(true)
    setMessage(null)
    try {
      // Her tıklama yeni bir idempotency anahtarı alır; ağ hatasında aynı istek
      // tekrar gönderilse bile sunucu ikinci teklif açmaz.
      const res = await placeBid(auctionId, userId, value, newIdempotencyKey())
      const auto = res.bids.find((b) => b.is_auto)
      setMessage({
        ok: true,
        text: auto
          ? `Teklifiniz alındı (${tl(value)}). ${userName(auto.bidder_id)} otomatik olarak ${tl(auto.amount)} ile karşılık verdi.`
          : `Teklifiniz alındı: ${tl(value)}`,
      })
      setAmount('')
    } catch (err) {
      setMessage({ ok: false, text: err.message })
    } finally {
      setPending(false)
    }
  }

  async function submitAutoBid(e) {
    e.preventDefault()
    if (!maxAmount) return
    setPending(true)
    setMessage(null)
    try {
      const res = await setAutoBid(auctionId, userId, Number(maxAmount))
      setMessage({
        ok: true,
        text:
          res.highest_bidder_id === userId
            ? `Otomatik teklif limiti kaydedildi (${tl(Number(maxAmount))}). Şu an öndesiniz: ${tl(res.current_price)}`
            : `Limit kaydedildi ama ${userName(res.highest_bidder_id)} daha yüksek bir limitle önde: ${tl(res.current_price)}`,
      })
      setMaxAmount('')
    } catch (err) {
      setMessage({ ok: false, text: err.message })
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="live">
      <section className="card product">
        <div className="product-head">
          <div>
            <div className="product-title">{auction.listing.title}</div>
            <div className="muted">
              {auction.listing.category} · {auction.listing.district}, {auction.listing.city} · Satıcı:{' '}
              {userName(auction.listing.seller_id)}
            </div>
          </div>
          <span className={`live-dot ${connected ? 'on' : ''}`}>{connected ? 'Canlı' : 'Bağlantı yok'}</span>
        </div>

        {auction.listing.description && <p className="description">{auction.listing.description}</p>}
        {auction.listing.defects && (
          <p className="defects">
            <strong>Belirtilen kusur:</strong> {auction.listing.defects}
          </p>
        )}

        <div className="price-row">
          <div className="price">
            <span className="price-label">{isClosed ? 'Kapanış fiyatı' : 'Güncel teklif'}</span>
            <span className="price-value">{tl(auction.current_price)}</span>
          </div>
          <Countdown endTime={auction.end_time} status={auction.status} serverNow={serverNow} />
        </div>

        {notice === 'extended' && (
          <div className="banner extended">Son dakika teklifi geldi: süre 2 dakika uzatıldı</div>
        )}
        {notice === 'outbid' && (
          <div className="banner outbid">Teklifiniz geçildi! Yeni fiyat: {tl(auction.current_price)}</div>
        )}

        {isClosed ? (
          <div className="banner closed">
            {auction.winner_id
              ? `Kazanan: ${userName(auction.winner_id)} (${tl(auction.current_price)}). Buluşma randevusu taslağı açıldı.`
              : 'Teklif gelmeden kapandı.'}
            {auction.winner_id === userId && ' Tebrikler, kazandınız!'}
          </div>
        ) : (
          <>
            <div className="leader">
              Önde: <strong>{userName(auction.highest_bidder_id)}</strong>
              {isLeader && <span className="you-lead">Şu an öndesiniz</span>}
            </div>

            {isSeller ? (
              <p className="muted">Bu ilanın satıcısısınız; kendi ilanınıza teklif veremezsiniz.</p>
            ) : (
              <>
                <form className="bid-form" onSubmit={submitBid}>
                  {/* min/step bilerek konmadı: kurallar sunucuda uygulanır, hatayı sunucu döner. */}
                  <input
                    type="number"
                    placeholder={`En az ${auction.min_next_bid.toLocaleString('tr-TR')}`}
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    aria-label="Teklif tutarı"
                  />
                  <button type="submit" className="bid-button" disabled={pending}>
                    {amount === '' ? `Teklif Ver (${tl(auction.min_next_bid)})` : 'Teklif Ver'}
                  </button>
                </form>
                <form className="auto-form" onSubmit={submitAutoBid}>
                  <input
                    type="number"
                    placeholder="Otomatik teklif üst limiti"
                    value={maxAmount}
                    onChange={(e) => setMaxAmount(e.target.value)}
                    aria-label="Otomatik teklif üst limiti"
                  />
                  <button type="submit" disabled={pending || !maxAmount}>
                    Limit Koy
                  </button>
                </form>
              </>
            )}
          </>
        )}

        {message && <div className={`message ${message.ok ? 'ok' : 'error'}`}>{message.text}</div>}
        <div className="rules muted">
          Minimum artış {tl(auction.min_increment)} · Başlangıç {tl(auction.start_price)}
        </div>
      </section>

      <BidHistory bids={auction.bids} currentUserId={userId} />
    </div>
  )
}
