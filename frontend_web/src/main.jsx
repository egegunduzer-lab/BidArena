import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// PWA: service worker yalnızca derlenmiş sürümde kaydedilir (geliştirmede
// önbellek, anlık yeniden yüklemeyi bozmasın). Tarayıcı güvenli bağlam
// (HTTPS ya da localhost) istemediği durumda kayıt atlanır.
if (import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
