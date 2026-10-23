import type { IncomingMessage, ServerResponse } from 'node:http'
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig, type Plugin } from 'vite'

function appEntryFallback(): Plugin {
  const middleware = (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    const url = req.url ?? ''
    const path = url.split('?')[0]

    if (path === '/app') {
      res.statusCode = 302
      res.setHeader('Location', '/app/')
      res.end()
      return
    }

    if (path.startsWith('/app/')) {
      const query = url.includes('?') ? url.slice(url.indexOf('?')) : ''
      req.url = `/app.html${query}`
    }

    next()
  }

  return {
    name: 'zhiying-app-entry-fallback',
    configureServer(server) {
      server.middlewares.use(middleware)
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware)
    },
  }
}

export default defineConfig({
  plugins: [vue(), tailwindcss(), appEntryFallback()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      input: {
        site: fileURLToPath(new URL('./index.html', import.meta.url)),
        app: fileURLToPath(new URL('./app.html', import.meta.url)),
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5288,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})
