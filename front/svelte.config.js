import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    // SPA: o HTML e servido estatico e todas as rotas caem no index.html (fallback).
    adapter: adapter({ pages: 'build', assets: 'build', fallback: 'index.html', strict: true }),
  },
  compilerOptions: { runes: true },
};

export default config;
