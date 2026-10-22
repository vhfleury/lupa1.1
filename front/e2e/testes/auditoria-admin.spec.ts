// Etapa 6.10: auditoria como administrador (revisão 6.4-6.9, item 6), custo dos resumos no
// relatório por usuário (item 7) e o aviso de "sessão encerrada ou expirada" depois de recarga
// completa. O admin é o criado em fluxos.spec.ts, compartilhado pela fixture global.
import { expect, test } from '@playwright/test';
import { contextoComo, lerConta } from './credenciais';

test.describe.serial('6.10 auditoria como admin e sessão', () => {
  test('admin vê eventos de todos os gabinetes e filtra por um deles', async ({ browser }) => {
    const { contexto, page } = await contextoComo(browser, 'admin');
    try {
      await page.goto('/auditoria');
      await expect(page.getByTestId('evento').first()).toBeVisible();
      const gabinete = page.getByLabel('Gabinete');
      await expect(gabinete).toBeVisible();
      await expect(gabinete).toHaveValue('');
      // Sem filtro: eventos de mais de um gabinete (e da cadeia global).
      await page.getByRole('button', { name: 'Carregar mais' }).click();
      const todos = await page
        .getByTestId('evento')
        .evaluateAll((linhas) => linhas.map((l) => l.getAttribute('data-gabinete') ?? ''));
      expect(new Set(todos).size).toBeGreaterThan(1);
      // Com filtro: só o escolhido.
      const escolhido = todos.find((g) => g !== '') ?? '';
      await gabinete.selectOption(escolhido);
      await page.getByRole('button', { name: 'Consultar' }).click();
      await expect(page.getByTestId('evento').first()).toBeVisible();
      const filtrados = await page
        .getByTestId('evento')
        .evaluateAll((linhas) => linhas.map((l) => l.getAttribute('data-gabinete')));
      expect(new Set(filtrados)).toEqual(new Set([escolhido]));
      // A API confirma: admin pode consultar qualquer gabinete.
      const api = await page.request.get(`/api/auditoria?gabinete_id=${escolhido}`);
      expect(api.status()).toBe(200);
    } finally {
      await contexto.close();
    }
  });

  test('relatório por usuário traz o custo estimado (chat e resumos do dossiê)', async ({
    browser,
  }) => {
    const { contexto, page } = await contextoComo(browser, 'admin');
    try {
      const desembargador = lerConta('desembargador-chat').usuario;
      const usuarios = (await (await page.request.get('/api/usuarios')).json()) as {
        id: string;
        nome_usuario: string;
      }[];
      const alvo = usuarios.find((u) => u.nome_usuario === desembargador);
      expect(alvo, 'desembargador do chat').toBeDefined();
      await page.goto('/auditoria');
      await page.getByLabel('Por').selectOption('usuario');
      await page.getByLabel('Identificador').fill(alvo?.id ?? '');
      await page.getByRole('button', { name: 'Gerar relatório' }).click();
      await expect(page.getByTestId('relatorio-uso')).toContainText('pergunta_chat');
      await expect(page.getByTestId('custo-estimado')).toContainText('Custo estimado');
      await expect(page.getByTestId('custo-estimado')).toContainText('tokens de entrada');
    } finally {
      await contexto.close();
    }
  });

  test('recarga completa sem sessão avisa "sessão encerrada ou expirada"', async ({ browser }) => {
    const { contexto, page } = await contextoComo(browser, 'admin');
    try {
      await page.goto('/usuarios');
      await expect(page.getByRole('heading', { name: 'Usuários' })).toBeVisible();
      // A sessão some (expirou ou foi revogada) e o usuário recarrega a página inteira: a memória
      // da SPA se perde, mas o marcador em sessionStorage diz que havia sessão neste separador.
      await contexto.clearCookies();
      await page.reload();
      await expect(page).toHaveURL(/\/login\?motivo=expirada$/);
      await expect(page.getByRole('status')).toContainText('Sessão encerrada ou expirada');
      // O marcador é consumido (aviso uma vez só) e nunca guarda dado da sessão.
      expect(await page.evaluate(() => sessionStorage.getItem('lupa.sessao-anterior'))).toBeNull();
      const chaves = await page.evaluate(() => Object.keys(sessionStorage));
      expect(chaves.filter((c) => c.startsWith('lupa.'))).toEqual([]);
    } finally {
      await contexto.close();
    }
    // Quem nunca entrou neste separador vê o login sem aviso.
    const novo = await browser.newContext();
    const pagina = await novo.newPage();
    await pagina.goto('/usuarios');
    await expect(pagina).toHaveURL(/\/login$/);
    await expect(pagina.getByText('Sessão encerrada ou expirada')).toHaveCount(0);
    await novo.close();
  });

  test('sair de propósito não mostra aviso de expiração, nem após recarregar', async ({
    browser,
  }) => {
    const { contexto, page } = await contextoComo(browser, 'admin');
    try {
      await page.goto('/');
      await page.getByRole('button', { name: 'Sair' }).click();
      await expect(page).toHaveURL(/\/login$/);
      await page.reload();
      await expect(page).toHaveURL(/\/login$/);
      await expect(page.getByText('Sessão encerrada ou expirada')).toHaveCount(0);
    } finally {
      await contexto.close();
    }
  });
});
