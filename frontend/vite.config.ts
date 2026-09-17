import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), {
    name: 'aegis-offline-shell',
    generateBundle(_options, bundle) {
      const assets = Object.keys(bundle).filter(name => /\.(js|css|svg|woff2?)$/.test(name)).map(name => '/' + name);
      this.emitFile({ type: 'asset', fileName: 'sw-assets.js', source: `self.AEGIS_BUILD=${JSON.stringify(Date.now().toString())};self.AEGIS_ASSETS=${JSON.stringify(assets)};self.AEGIS_API=${JSON.stringify(process.env.VITE_API_BASE_URL || '/api')};` });
    },
  }],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: process.env.AEGIS_BACKEND_URL || 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: { groups: [{ name: 'maplibre', test: /node_modules[\\/]maplibre-gl/ }] },
      },
    },
  },
})
