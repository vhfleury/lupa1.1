// Etapa 7.9: capturas de tela dos guias (docs/imagens). Reaproveita a configuração da suíte E2E e
// acrescenta o projeto "capturas", que depende de "fluxos" (primeiro acesso das contas sintéticas).
// Rodar só por front/scripts/capturas.sh. Não altera a suíte normal (playwright.config.ts).
import { defineConfig } from '@playwright/test';
import base from './playwright.config';

const projetos = (base.projects ?? []).filter((p) => p.name === 'fluxos');

export default defineConfig({
  ...base,
  testDir: '.',
  projects: [
    ...projetos.map((p) => ({ ...p, testDir: './testes' })),
    {
      name: 'capturas',
      testDir: '.',
      testMatch: /capturas\.spec\.ts$/,
      dependencies: ['fluxos'],
      use: { ...(projetos[0]?.use ?? {}), viewport: { width: 1200, height: 760 } },
    },
  ],
});
