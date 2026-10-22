import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [sveltekit()],
  ...(process.env['VITEST'] ? { resolve: { conditions: ['browser'] } } : {}),
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    setupFiles: ['src/testes-setup.ts'],
  },
});
