import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        vnc: resolve(__dirname, 'vnc.html'),
      },
    },
  },
  server: { proxy: { '/api': 'http://localhost:9000', '/view': 'http://localhost:9000' } },
})
