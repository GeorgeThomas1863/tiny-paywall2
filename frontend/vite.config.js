import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Ports come from the root .env (shared with the backend); defaults match docker-compose.
const rootDir = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, rootDir, '')
  const frontendPort = Number(env.FRONTEND_PORT) || 3000
  const backendPort = Number(env.BACKEND_PORT) || 8000
  const apiUrl = env.VITE_API_URL || `http://localhost:${backendPort}`

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: frontendPort,
    },
    define: {
      'import.meta.env.VITE_API_URL': JSON.stringify(apiUrl),
    },
  }
})
