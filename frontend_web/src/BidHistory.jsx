import { userName } from './demoUsers'

const time = (iso) =>
  new Date(iso).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export default function BidHistory({ bids, currentUserId }) {
  return (
    <section className="card history">
      <h2>Teklif Geçmişi</h2>
      {bids.length === 0 ? (
        <p className="muted">Henüz teklif yok.</p>
      ) : (
        <ol className="history-list">
          {bids.map((b, i) => (
            <li key={b.id} className={`${i === 0 ? 'top' : ''} ${b.bidder_id === currentUserId ? 'mine' : ''}`}>
              <span className="who">
                {userName(b.bidder_id)}
                {b.bidder_id === currentUserId && ' (siz)'}
                {b.is_auto && <span className="badge">otomatik</span>}
              </span>
              <span className="amount">{b.amount.toLocaleString('tr-TR')} ₺</span>
              <span className="when">{time(b.created_at)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
