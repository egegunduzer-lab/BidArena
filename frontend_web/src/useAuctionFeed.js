import { useCallback, useEffect, useRef, useState } from 'react'
import { auctionSocketUrl } from './api'

const RECONNECT_MS = 1500
const PING_MS = 25000

/**
 * Bir açık artırmanın canlı durumunu WebSocket üzerinden izler (Observer).
 *
 * Bağlanınca sunucu SNAPSHOT gönderir; sonra her kabul edilen teklifte
 * NEW_BID, kapanışta AUCTION_CLOSED gelir. Ekrandaki fiyat yalnızca bu
 * olaylardan güncellenir; böylece teklifi veren de izleyen de aynı veriyi görür.
 *
 * Geri sayım istemci saatine değil sunucu saatine göre yapılır:
 * her mesajdaki server_time ile yerel saat arasındaki fark saklanır.
 */
export function useAuctionFeed(auctionId, userId) {
  const [auction, setAuction] = useState(null)
  const [connected, setConnected] = useState(false)
  const [notice, setNotice] = useState(null)
  const clockOffset = useRef(0)
  const leaderRef = useRef(null) // "teklifiniz geçildi" tespiti için önceki lider
  // Kullanıcı değişince ekran yeniden kurulur (App'teki key), bu yüzden sabit.
  const userRef = useRef(userId)

  useEffect(() => {
    if (!auctionId) return undefined
    let socket
    let retryTimer
    let pingTimer
    let noticeTimer
    let stopped = false

    const showNotice = (type) => {
      setNotice(type)
      clearTimeout(noticeTimer)
      noticeTimer = setTimeout(() => setNotice(null), 4000)
    }

    const syncClock = (serverTime) => {
      clockOffset.current = new Date(serverTime).getTime() - Date.now()
    }

    const handle = (msg) => {
      switch (msg.event) {
        case 'SNAPSHOT':
          syncClock(msg.server_time)
          leaderRef.current = msg.highest_bidder_id
          setAuction(msg)
          break
        case 'NEW_BID':
          syncClock(msg.server_time)
          if (leaderRef.current === userRef.current && msg.highest_bidder_id !== userRef.current) {
            showNotice('outbid')
            navigator.vibrate?.([120, 60, 120]) // telefonda titreşim
          }
          leaderRef.current = msg.highest_bidder_id
          setAuction((prev) =>
            prev && {
              ...prev,
              current_price: msg.current_price,
              min_next_bid: msg.min_next_bid,
              highest_bidder_id: msg.highest_bidder_id,
              end_time: msg.end_time,
              // Yeni teklifler en üstte; olaydaki sıra işlenme sırasıdır.
              bids: [...[...msg.bids].reverse(), ...prev.bids].slice(0, 50),
            },
          )
          if (msg.extended) showNotice('extended')
          break
        case 'AUCTION_STARTED':
          setAuction((prev) => prev && { ...prev, status: 'ACTIVE' })
          break
        case 'AUCTION_CLOSED':
          setAuction((prev) => prev && { ...prev, status: 'CLOSED', winner_id: msg.winner_id })
          break
        default:
          break
      }
    }

    const connect = () => {
      socket = new WebSocket(auctionSocketUrl(auctionId))
      socket.onopen = () => {
        setConnected(true)
        pingTimer = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send('ping')
        }, PING_MS)
      }
      socket.onmessage = (e) => handle(JSON.parse(e.data))
      socket.onclose = () => {
        setConnected(false)
        clearInterval(pingTimer)
        // Bağlantı koparsa yeniden bağlan; sunucu yeni bir SNAPSHOT gönderir.
        if (!stopped) retryTimer = setTimeout(connect, RECONNECT_MS)
      }
    }

    connect()
    return () => {
      stopped = true
      clearTimeout(retryTimer)
      clearTimeout(noticeTimer)
      clearInterval(pingTimer)
      socket?.close()
    }
  }, [auctionId])

  const serverNow = useCallback(() => Date.now() + clockOffset.current, [])

  return { auction, connected, notice, serverNow }
}
