import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  server: { host: 'localhost', port: 5173, strictPort: true },
  build: { outDir: 'dist', rollupOptions: { input: { index: 'index.html', tracker: 'tracker.html' } } },
});
