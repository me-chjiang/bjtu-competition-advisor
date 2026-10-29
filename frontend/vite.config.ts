import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';

const backend = 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': backend },
  },
  test: { environment: 'jsdom' },
});
