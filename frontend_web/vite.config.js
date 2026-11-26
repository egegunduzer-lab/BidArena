import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Geliştirmede /api ve /ws istekleri FastAPI backend'ine yönlendirilir.
// Böylece tarayıcı tek bir adres görür (CORS ayarı gerekmez).
const BACKEND = process.env.BIDARENA_BACKEND ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': BACKEND,
      '/ws': { target: BACKEND, ws: true },
    },
  },
})
