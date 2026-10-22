import { defineConfig, devices } from '@playwright/test';

// Um único worker e ordem fixa: os fluxos dependem uns dos outros (o admin cria o gabinete e o
// desembargador; o desembargador cria o assessor), como no uso real.
// 6.10: dois projetos. "fluxos" (6.1 a 6.9) faz o primeiro acesso de cada conta e a guarda pela
// fixture global (testes/credenciais.ts); "finais" (segurança, acessibilidade, auditoria como
// admin) depende dele e reutiliza as contas.
const comum = { ...devices['Desktop Chrome'] };

export default defineConfig({
  testDir: './testes',
  globalSetup: './testes/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env['LUPA_E2E_URL'] ?? 'https://proxy:8443',
    ignoreHTTPSErrors: true,
    locale: 'pt-BR',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'fluxos', testMatch: /(chat-auditoria|fluxos|processos)\.spec\.ts$/, use: comum },
    {
      name: 'finais',
      testMatch: /(acessibilidade|auditoria-admin|seguranca)\.spec\.ts$/,
      dependencies: ['fluxos'],
      use: comum,
    },
  ],
});
