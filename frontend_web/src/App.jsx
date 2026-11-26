import { useEffect, useState } from 'react'
import './App.css'
import { listAuctions } from './api'
import { DEMO_USERS } from './demoUsers'
import LiveAuction from './LiveAuction'

// Seçimler adres çubuğunda tutulur (?auction=1&user=6). Böylece iki sekme
// farklı kullanıcılarla açılıp canlı teklif yarışı gösterilebilir.
function readParam(name, fallback) {
  const value = Number(new URLSearchParams(window.location.search).get(name))
  return Number.isInteger(value) && value > 0 ? value : fallback
}

function writeParams(params) {
  const url = new URL(window.location.href)
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  window.history.replaceState(null, '', url)
}

const STATUS_LABEL = { ACTIVE: 'canlı', SCHEDULED: 'başlayacak', CLOSED: 'kapandı' }

function App() {
  const [auctions, setAuctions] = useState([])
  const [auctionId, setAuctionId] = useState(readParam('auction', null))
  const [userId, setUserId] = useState(readParam('user', DEMO_USERS[0].id))
  const [error, setError] = useState(null)

  useEffect(() => {
    listAuctions()
      .then((rows) => {
        setAuctions(rows)
        setAuctionId((current) => current ?? rows[0]?.auction_id ?? null)
      })
      .catch(() => setError('Backend\'e ulaşılamadı. Sunucu (uvicorn) çalışıyor mu?'))
  }, [])

  useEffect(() => {
    if (auctionId) writeParams({ auction: auctionId, user: userId })
  }, [auctionId, userId])

  return (
    <div className="app">
      <header className="app-header">
        <h1>BidArena - Canlı Teklif Ekranı</h1>
        <div className="controls">
          <label>
            Açık artırma
            <select value={auctionId ?? ''} onChange={(e) => setAuctionId(Number(e.target.value))}>
              {auctions.map((a) => (
                <option key={a.auction_id} value={a.auction_id}>
                  #{a.auction_id} {a.title} ({STATUS_LABEL[a.status] ?? a.status})
                </option>
              ))}
            </select>
          </label>
          <label>
            Kullanıcı (demo)
            <select value={userId} onChange={(e) => setUserId(Number(e.target.value))}>
              {DEMO_USERS.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name} ({u.note})
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      <main>
        {error && <div className="card error-card">{error}</div>}
        {/* key: açık artırma ya da kullanıcı değişince ekran sıfırdan kurulur (form temizlenir). */}
        {auctionId && <LiveAuction key={`${auctionId}-${userId}`} auctionId={auctionId} userId={userId} />}
      </main>
    </div>
  )
}

export default App
