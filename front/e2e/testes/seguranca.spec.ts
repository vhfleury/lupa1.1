// Etapa 6.10: segurança do front. (1) Cabeçalhos do proxy, com a CSP sem afrouxar; (2) nenhuma
// violação de CSP nas telas (nada inline); (3) texto hostil dos autos (processo sintético com
// `<script>`, link Markdown e URL crua numa página) aparece como texto puro: nada executa e
// nenhuma URL do texto vira link clicável (prompt-injection.md, seção 6).
import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { contextoComo } from './credenciais';

const HOSTIL = process.env['LUPA_E2E_HOSTIL_PROCESSO'] ?? '';
const CHAT = process.env['LUPA_E2E_CHAT_PROCESSO'] ?? '';
const PROC = process.env['LUPA_E2E_PROC_ID'] ?? '';

const ROTAS = ['/', '/login', '/processos', '/inicio.js', '/favicon.svg', '/api/saude'];

function lerCsp(valor: string): Map<string, string[]> {
  const mapa = new Map<string, string[]>();
  for (const parte of valor.split(';')) {
    const [nome, ...fontes] = parte.trim().split(/\s+/);
    if (nome) mapa.set(nome.toLowerCase(), fontes);
  }
  return mapa;
}

async function vigiarCsp(contexto: BrowserContext): Promise<void> {
  await contexto.addInitScript(() => {
    const w = window as unknown as { __violacoes: string[] };
    w.__violacoes = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      w.__violacoes.push(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
}

async function violacoes(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __violacoes?: string[] }).__violacoes ?? []);
}

test.describe('6.10 segurança do front', () => {
  test.beforeAll(() => {
    expect(HOSTIL, 'rode via front/scripts/e2e.sh (semeia o processo hostil)').not.toBe('');
  });

  test('cabeçalhos de segurança em todas as rotas, com CSP restritiva', async ({ request }) => {
    for (const rota of ROTAS) {
      const resposta = await request.get(rota);
      const h = resposta.headers();
      expect(h['strict-transport-security'], rota).toMatch(/max-age=(\d{8,}|[2-9]\d{7}|1[6-9]\d{6})/);
      expect(h['permissions-policy'], rota).toContain('camera=()');
      expect(h['permissions-policy'], rota).toContain('microphone=()');
      expect(h['permissions-policy'], rota).toContain('geolocation=()');
      expect(h['cross-origin-opener-policy'], rota).toBe('same-origin');
      expect(h['x-content-type-options'], rota).toBe('nosniff');
      expect(h['referrer-policy'], rota).toBe('no-referrer');
      expect(h['x-frame-options'], rota).toBe('DENY');
      expect(h['server'], rota).toBeUndefined();
      const csp = lerCsp(h['content-security-policy'] ?? '');
      expect(csp.get('default-src'), rota).toEqual(["'none'"]);
      expect(csp.get('script-src'), rota).toEqual(["'self'"]);
      // Única exceção: o estilo fixo do anunciador de rota do SvelteKit, por hash.
      expect(csp.get('style-src'), rota).toEqual(["'self'", "'unsafe-hashes'", "'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo='"]);
      expect(csp.get('object-src'), rota).toEqual(["'none'"]);
      expect(csp.get('frame-ancestors'), rota).toEqual(["'none'"]);
      expect(csp.get('base-uri'), rota).toEqual(["'none'"]);
      expect(csp.get('form-action'), rota).toEqual(["'self'"]);
      const todas = [...csp.values()].flat();
      for (const frouxo of ["'unsafe-inline'", "'unsafe-eval'", '*', 'data:', 'blob:', 'http:']) {
        expect(todas, `${rota} sem ${frouxo}`).not.toContain(frouxo);
      }
    }
  });

  test('index.html sem script nem estilo inline; o HTML vindo da API nunca é executado', async ({
    request,
  }) => {
    const html = await (await request.get('/login')).text();
    expect(html).toContain('<script src="/inicio.js"></script>');
    expect(html).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>/);
    expect(html).not.toMatch(/\sstyle=|<style/);
    const inicio = await request.get('/inicio.js');
    expect(inicio.headers()['content-type']).toMatch(/javascript/);
  });

  test('nenhuma violação de CSP ao navegar pelas telas', async ({ browser }) => {
    const encontradas: string[] = [];
    for (const [papel, caminhos] of [
      ['assessor-processos', ['/', '/processos', `/processos/${PROC}`, `/processos/${PROC}/dossie`, `/processos/${PROC}/visualizador`, `/processos/${PROC}/validacoes`]],
      ['desembargador-chat', [`/processos/${CHAT}/chat`, '/auditoria', '/usuarios']],
    ] as const) {
      const { contexto, page } = await contextoComo(browser, papel);
      await vigiarCsp(contexto);
      const console: string[] = [];
      page.on('console', (m) => {
        if (/Content Security Policy|Refused to/i.test(m.text())) console.push(m.text());
      });
      try {
        for (const caminho of caminhos) {
          await page.goto(caminho);
          await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
          await expect(page.getByText(/^Carregando/)).toHaveCount(0, { timeout: 30_000 });
          // Interações que mexem em estilo dinâmico (zoom do visualizador, tema).
          if (caminho.endsWith('/visualizador')) {
            await page.getByRole('button', { name: 'Aumentar zoom' }).click();
          }
          await page.getByLabel('Tema').selectOption('escuro');
          encontradas.push(...(await violacoes(page)).map((v) => `${caminho}: ${v}`));
        }
        encontradas.push(...console);
      } finally {
        await contexto.close();
      }
    }
    expect(encontradas).toEqual([]);
  });

  test('texto hostil dos autos sai como texto: sem script executado, sem link externo', async ({
    browser,
  }) => {
    const { contexto, page } = await contextoComo(browser, 'desembargador-chat');
    await vigiarCsp(contexto);
    try {
      await page.goto(`/processos/${HOSTIL}/chat`);
      await expect(page.getByRole('heading', { name: 'Conversa atual' })).toBeVisible();
      await page.getByLabel('Pergunta', { exact: true }).fill('Quando a defesa foi intimada?');
      await page.getByRole('button', { name: 'Perguntar' }).click();
      const resposta = page.getByTestId('conversa-atual').getByTestId('mensagem').last();
      await expect(resposta).toHaveAttribute('data-status', 'respondida', { timeout: 30_000 });
      const citacao = resposta.getByTestId('citacao');
      await expect(citacao).toBeVisible({ timeout: 30_000 });
      // O trecho citado traz os padrões hostis literalmente, como texto.
      await expect(citacao).toContainText('<script>window.__lupaXss = 1</script>');
      await expect(citacao).toContainText('[link](http://x)');
      await expect(citacao).toContainText('http://exemplo');
      // Nada executou e nenhum elemento foi criado a partir do texto.
      expect(await page.evaluate(() => (window as unknown as { __lupaXss?: number }).__lupaXss)).toBeUndefined();
      expect(await page.locator('main script').count()).toBe(0);
      expect(await page.locator('a[href^="http"]').count()).toBe(0);
      expect(await page.locator('a[href*="exemplo"], a[href="http://x"]').count()).toBe(0);
      // O único link da citação é interno (ids), sem texto dos autos na URL.
      const destino = (await citacao.getAttribute('href')) ?? '';
      expect(destino).toMatch(new RegExp(`^/processos/${HOSTIL}/visualizador\\?`));
      expect(destino).not.toMatch(/script|exemplo|link/);
      // Recarregando, o histórico também vem como texto.
      await page.reload();
      await expect(page.getByTestId('citacao').first()).toContainText('[link](http://x)');
      expect(await page.locator('a[href^="http"]').count()).toBe(0);
      expect(await violacoes(page)).toEqual([]);
    } finally {
      await contexto.close();
    }
  });
});
