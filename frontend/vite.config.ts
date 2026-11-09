import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Keep development requests on the same origin. FastAPI remains at :8000.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/analyses': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000' } },
})
