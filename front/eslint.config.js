import js from '@eslint/js';
import svelte from 'eslint-plugin-svelte';
import globals from 'globals';
import ts from 'typescript-eslint';

export default ts.config(
  js.configs.recommended,
  ...ts.configs.strict,
  ...svelte.configs['flat/recommended'],
  {
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    files: ['**/*.svelte', '**/*.svelte.ts'],
    languageOptions: { parserOptions: { parser: ts.parser } },
  },
  {
    rules: {
      // Conteudo vindo da API nunca vira HTML.
      'svelte/no-at-html-tags': 'error',
      'no-console': 'error',
    },
  },
  { ignores: ['build/', '.svelte-kit/', 'node_modules/', 'e2e/'] },
);
