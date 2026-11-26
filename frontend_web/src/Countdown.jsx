import { useEffect, useState } from 'react'

function format(ms) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

// Kalan süre, sunucu saatine göre (serverNow) hesaplanır.
export default function Countdown({ endTime, status, serverNow, extensionWindowSec = 120 }) {
  const [now, setNow] = useState(serverNow())

  useEffect(() => {
    const timer = setInterval(() => setNow(serverNow()), 250)
    return () => clearInterval(timer)
  }, [serverNow])

  if (status === 'CLOSED') return <div className="countdown closed">Açık artırma kapandı</div>

  const remaining = new Date(endTime).getTime() - now
  if (remaining <= 0) return <div className="countdown closing">Süre doldu, kapanıyor…</div>

  const lastWindow = remaining <= extensionWindowSec * 1000
  return (
    <div className={`countdown ${lastWindow ? 'last-window' : ''}`}>
      <span className="countdown-label">Kalan süre</span>
      <span className="countdown-value">{format(remaining)}</span>
      {lastWindow && <span className="countdown-hint">Son 2 dakika: geçerli teklif süreyi uzatır</span>}
    </div>
  )
}
