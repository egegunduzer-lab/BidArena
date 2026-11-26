// BidArena service worker.
//
// Yalnızca uygulama kabuğunu (HTML, derlenmiş JS/CSS, ikonlar) önbelleğe alır;
// böylece uygulama ana ekrandan hızlı açılır. Canlı veriye (/api, /ws) asla
// dokunmaz: fiyat ve teklifler her zaman sunucudan gelir, önbellekten eski
// fiyat gösterilmez.
const CACHE = 'bidarena-shell-v1'
const SHELL = ['/', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')) return // canlı veri

  if (request.mode === 'navigate') {
    // Sayfa: önce ağ (en güncel sürüm), ağ yoksa önbellekteki kabuk.
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone()
          caches.open(CACHE).then((cache) => cache.put('/', copy))
          return res
        })
        .catch(() => caches.match('/')),
    )
    return
  }

  if (url.pathname.startsWith('/assets/') || SHELL.includes(url.pathname)) {
    // Derlenmiş dosyaların adında içerik özeti var; önbellekten vermek güvenli.
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((res) => {
            const copy = res.clone()
            caches.open(CACHE).then((cache) => cache.put(request, copy))
            return res
          }),
      ),
    )
  }
})
