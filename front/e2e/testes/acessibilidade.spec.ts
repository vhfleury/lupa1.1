// Etapa 6.10: acessibilidade das telas principais. Varredura automática com axe-core (WCAG 2.1
// A/AA) em cada tela, nos temas claro e escuro, sem violação séria ou crítica (inclui contraste);
// navegação por teclado com foco visível; alternância manual de tema persistida só no
// localStorage. Reutiliza as contas criadas pelos fluxos (testes/credenciais.ts).
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Browser, type Page } from '@playwright/test';
import { contextoComo, type Papel } from './credenciais';

const PROC = process.env['LUPA_E2E_PROC_ID'] ?? '';
const CHAT = process.env['LUPA_E2E_CHAT_PROCESSO'] ?? '';
const TEMAS = ['claro', 'escuro'] as const;
const GRAVES = new Set(['serious', 'critical']);

interface Tela {
  papel: Papel | null;
  caminho: () => string;
  titulo: RegExp;
}

const TELAS: Tela[] = [
  { papel: null, caminho: () => '/login', titulo: /^Lupa$/ },
  { papel: 'assessor-processos', caminho: () => '/', titulo: /./ },
  { papel: 'assessor-processos', caminho: () => '/processos', titulo: /^Processos$/ },
  { papel: 'assessor-processos', caminho: () => `/processos/${PROC}`, titulo: /./ },
  { papel: 'assessor-processos', caminho: () => `/processos/${PROC}/dossie`, titulo: /Dossiê/ },
  { papel: 'assessor-processos', caminho: () => `/processos/${PROC}/visualizador`, titulo: /Visualizador/ },
  { papel: 'assessor-processos', caminho: () => `/processos/${PROC}/validacoes`, titulo: /Validações/ },
  { papel: 'desembargador-chat', caminho: () => `/processos/${CHAT}/chat`, titulo: /Chat sobre os autos/ },
  { papel: 'desembargador-chat', caminho: () => '/auditoria', titulo: /Auditoria/ },
  { papel: 'desembargador-chat', caminho: () => '/usuarios', titulo: /Usuários/ },
  { papel: 'admin', caminho: () => '/gabinetes', titulo: /Gabinetes/ },
  { papel: 'admin', caminho: () => '/usuarios', titulo: /Usuários/ },
  { papel: 'admin', caminho: () => '/auditoria', titulo: /Auditoria/ },
];

async function abrir(browser: Browser, papel: Papel | null, tema: (typeof TEMAS)[number]) {
  if (papel) return contextoComo(browser, papel, { tema });
  const contexto = await browser.newContext();
  await contexto.addInitScript((t) => window.localStorage.setItem('lupa.tema', t), tema);
  return { contexto, page: await contexto.newPage() };
}

async function esperarCarregada(page: Page, titulo: RegExp): Promise<void> {
  await expect(page.getByRole('heading', { level: 1 }).first()).toHaveText(titulo);
  await expect(page.getByText(/^Carregando/)).toHaveCount(0, { timeout: 30_000 });
}

test.describe('6.10 acessibilidade', () => {
  test.beforeAll(() => {
    expect(PROC, 'rode via front/scripts/e2e.sh').not.toBe('');
    expect(CHAT).not.toBe('');
  });

  for (const tema of TEMAS) {
    test(`axe sem violação séria ou crítica em todas as telas (tema ${tema})`, async ({
      browser,
    }) => {
      const achados: string[] = [];
      for (const tela of TELAS) {
        const { contexto, page } = await abrir(browser, tela.papel, tema);
        try {
          await page.goto(tela.caminho());
          await esperarCarregada(page, tela.titulo);
          await expect(page.locator('html')).toHaveAttribute('data-tema', tema);
          const resultado = await new AxeBuilder({ page })
            .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
            .analyze();
          for (const v of resultado.violations.filter((v) => GRAVES.has(v.impact ?? ''))) {
            const alvos = v.nodes.map((n) => n.target.join(' ')).slice(0, 5).join(' | ');
            achados.push(`${tela.caminho()} [${tema}] ${v.id} (${v.impact}): ${alvos}`);
          }
        } finally {
          await contexto.close();
        }
      }
      console.log(`axe (${tema}): ${TELAS.length} telas, ${achados.length} violações graves`);
      expect(achados, achados.join('\n')).toEqual([]);
    });
  }

  test('login inteiro pelo teclado: pular para o conteúdo, rótulos e foco visível', async ({
    page,
  }) => {
    await page.goto('/login');
    await expect(page.getByLabel('Usuário')).toBeVisible();
    // Começa do topo do documento: o primeiro Tab cai no "pular para o conteúdo".
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    await page.keyboard.press('Tab');
    const pular = page.getByRole('link', { name: 'Pular para o conteúdo' });
    await expect(pular).toBeFocused();
    await expect(pular).toBeInViewport();
    expect(await focoVisivel(page)).toBe(true);
    const focados: string[] = [];
    for (let i = 0; i < 4; i += 1) {
      await page.keyboard.press('Tab');
      focados.push(await descreverFoco(page));
    }
    expect(focados).toEqual(['input:Usuário', 'input:Senha', 'button:Continuar', 'select:Tema']);
    // Enviar com Enter, sem mouse: campos obrigatórios vazios não saem do lugar.
    await page.getByLabel('Usuário').focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/login/);
  });

  test('telas internas pelo teclado: menu, sair, tema e conteúdo com foco visível', async ({
    browser,
  }) => {
    const { contexto, page } = await contextoComo(browser, 'desembargador-chat');
    try {
      await page.goto('/');
      await expect(page.getByTestId('usuario-nome')).toBeVisible();
      const vistos = new Set<string>();
      for (let i = 0; i < 12; i += 1) {
        await page.keyboard.press('Tab');
        vistos.add(await descreverFoco(page));
      }
      for (const esperado of ['a:Pular para o conteúdo', 'a:Lupa', 'select:Tema', 'button:Sair', 'a:Processos', 'a:Auditoria']) {
        expect([...vistos]).toContain(esperado);
      }
      // Pular para o conteúdo leva o foco ao <main>.
      await page.goto('/');
      await page.getByRole('link', { name: 'Pular para o conteúdo' }).focus();
      await page.keyboard.press('Enter');
      await expect(page.locator('main#conteudo')).toBeFocused();
      // Navega até Processos só com Tab e Enter.
      const menu = page.getByRole('navigation', { name: 'Menu principal' });
      const processos = menu.getByRole('link', { name: 'Processos' });
      for (let i = 0; i < 15 && !(await processos.evaluate((el) => el === document.activeElement)); i += 1) {
        await page.keyboard.press('Tab');
      }
      await expect(processos).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(/\/processos$/);
      // Chat: campo de pergunta rotulado e alcançável; o visualizador navega por setas.
      await page.goto(`/processos/${CHAT}/chat`);
      await expect(page.getByLabel('Pergunta', { exact: true })).toBeVisible();
      await page.getByLabel('Pergunta', { exact: true }).focus();
      expect(await descreverFoco(page)).toBe('textarea:Pergunta');
    } finally {
      await contexto.close();
    }
  });

  test('visualizador: página muda pelas setas com o foco na moldura', async ({ browser }) => {
    const { contexto, page } = await contextoComo(browser, 'assessor-processos');
    try {
      await page.goto(`/processos/${PROC}/visualizador`);
      const moldura = page.getByTestId('moldura-pagina');
      await expect(moldura).toBeVisible();
      await moldura.focus();
      await expect(moldura).toBeFocused();
      expect(await focoVisivel(page)).toBe(true);
      await page.keyboard.press('+');
      await expect(page.getByTestId('zoom')).not.toHaveText('100%');
      await page.keyboard.press('-');
      await expect(page.getByTestId('zoom')).toHaveText('100%');
    } finally {
      await contexto.close();
    }
  });

  test('tema manual: claro, escuro e sistema, persistido só no localStorage', async ({
    browser,
  }) => {
    const contexto = await browser.newContext({ colorScheme: 'dark' });
    const page = await contexto.newPage();
    try {
      await page.goto('/login');
      const fundo = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      const seletor = page.getByLabel('Tema');
      await expect(seletor).toHaveValue('sistema');
      expect(await page.locator('html').getAttribute('data-tema')).toBeNull();
      const escuroDoSistema = await fundo();
      await seletor.selectOption('claro');
      await expect(page.locator('html')).toHaveAttribute('data-tema', 'claro');
      const claro = await fundo();
      expect(claro).not.toBe(escuroDoSistema);
      expect(await page.evaluate(() => localStorage.getItem('lupa.tema'))).toBe('claro');
      // Recarga completa: o tema vem do localStorage antes do primeiro desenho (inicio.js).
      await page.reload();
      await expect(page.locator('html')).toHaveAttribute('data-tema', 'claro');
      await expect(page.getByLabel('Tema')).toHaveValue('claro');
      expect(await fundo()).toBe(claro);
      await page.getByLabel('Tema').selectOption('escuro');
      expect(await fundo()).toBe(escuroDoSistema);
      await page.getByLabel('Tema').selectOption('sistema');
      expect(await page.evaluate(() => localStorage.getItem('lupa.tema'))).toBeNull();
      // Nada de tema em cookie (nem vai ao servidor).
      expect((await contexto.cookies()).map((c) => c.name)).not.toContain('lupa.tema');
    } finally {
      await contexto.close();
    }
  });
});

async function focoVisivel(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return false;
    const estilo = getComputedStyle(el);
    return estilo.outlineStyle !== 'none' && Number.parseFloat(estilo.outlineWidth) >= 2;
  });
}

/** "tag:nome acessível" do elemento focado; falha se o foco não for visível. */
async function descreverFoco(page: Page): Promise<string> {
  const descricao = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return 'body:';
    const id = el.getAttribute('id');
    const rotulo =
      el.getAttribute('aria-label') ??
      (id ? document.querySelector(`label[for="${id}"]`)?.textContent : null) ??
      el.textContent ??
      '';
    return `${el.tagName.toLowerCase()}:${rotulo.trim().replace(/\s+/g, ' ')}`;
  });
  if (descricao !== 'body:') expect(await focoVisivel(page), `foco visível em ${descricao}`).toBe(true);
  return descricao;
}
