// Fluxos ponta a ponta das subetapas 6.1 a 6.3 contra a API real (pelo proxy, mesmo origin).
// O administrador vem de scripts/e2e_preparar.py (senha temporária gerada na hora); todos os
// demais usuários são criados pela própria interface. O MFA é resolvido calculando o TOTP a
// partir da URI otpauth:// exibida na tela.
import { randomBytes } from 'node:crypto';
import { expect, test, type Page } from '@playwright/test';
import { guardarConta } from './credenciais';
import { Autenticador, segredoDaUri } from './totp';

const ADMIN_USUARIO = process.env['LUPA_E2E_ADMIN_USUARIO'] ?? '';
const ADMIN_SENHA = process.env['LUPA_E2E_ADMIN_SENHA'] ?? '';
const SUFIXO = randomBytes(3).toString('hex');
const GABINETE = `Gabinete E2E ${SUFIXO}`;
const DESEMBARGADOR = `des.e2e.${SUFIXO}`;
const ASSESSOR = `ass.e2e.${SUFIXO}`;
const MENSAGEM_CREDENCIAIS = 'Usuário ou senha inválidos.';
const MENSAGEM_BLOQUEIO = /Muitas tentativas/;

interface Conta {
  usuario: string;
  senha: string;
  autenticador: Autenticador;
}

const contas: Record<string, Conta> = {};
let senhaTemporariaDesembargador = '';
let senhaTemporariaAssessor = '';

function senhaNova(): string {
  return `frase-e2e-${randomBytes(9).toString('base64url')}-lupa`;
}

function conta(nome: string): Conta {
  const encontrada = contas[nome];
  if (!encontrada) throw new Error(`conta ${nome} ainda não criada`);
  return encontrada;
}

async function enviarSenha(page: Page, usuario: string, senha: string): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Usuário').fill(usuario);
  await page.getByLabel('Senha', { exact: true }).fill(senha);
  await page.getByRole('button', { name: 'Continuar' }).click();
}

async function primeiroAcesso(page: Page, usuario: string, temporaria: string): Promise<Conta> {
  await enviarSenha(page, usuario, temporaria);
  await expect(page.getByRole('heading', { name: 'Cadastre o autenticador' })).toBeVisible();
  await expect(page.getByRole('img', { name: /QR code para cadastrar/ })).toBeVisible();
  const uri = (await page.getByTestId('uri-mfa').textContent()) ?? '';
  const segredo = segredoDaUri(uri.trim());
  await expect(page.getByTestId('segredo-mfa')).toHaveText(segredo);
  const autenticador = new Autenticador(segredo);
  await page.getByLabel('Código de 6 dígitos').fill(await autenticador.proximo());
  await page.getByRole('button', { name: 'Confirmar autenticador' }).click();
  await expect(page).toHaveURL(/\/trocar-senha$/);
  await expect(page.getByText(/defina uma senha pessoal/)).toBeVisible();
  const senha = senhaNova();
  await page.getByLabel('Senha atual').fill(temporaria);
  await page.getByLabel('Nova senha', { exact: true }).fill(senha);
  await page.getByLabel('Confirme a nova senha').fill(senha);
  await page.getByRole('button', { name: 'Salvar nova senha' }).click();
  await expect(page.getByTestId('usuario-nome')).toHaveText(usuario);
  const nova = { usuario, senha, autenticador };
  contas[usuario] = nova;
  return nova;
}

async function entrar(page: Page, c: Conta): Promise<void> {
  await enviarSenha(page, c.usuario, c.senha);
  await expect(page.getByRole('heading', { name: 'Verificação em duas etapas' })).toBeVisible();
  await page.getByLabel('Código de 6 dígitos').fill(await c.autenticador.proximo());
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByTestId('usuario-nome')).toHaveText(c.usuario);
}

async function sair(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Sair' }).click();
  await expect(page).toHaveURL(/\/login$/);
}

async function lerSenhaTemporaria(page: Page): Promise<string> {
  const valor = ((await page.getByTestId('senha-temporaria-valor').textContent()) ?? '').trim();
  expect(valor.length).toBeGreaterThanOrEqual(12);
  await expect(page.getByText('não será exibida de novo')).toBeVisible();
  await page.getByRole('button', { name: /Já anotei/ }).click();
  await expect(page.getByTestId('senha-temporaria')).toHaveCount(0);
  await expect(page.getByText(valor)).toHaveCount(0);
  return valor;
}

async function alerta(page: Page): Promise<string> {
  const elemento = page.getByRole('alert');
  await expect(elemento).toBeVisible();
  return ((await elemento.textContent()) ?? '').trim();
}

function linha(page: Page, usuario: string) {
  return page.locator(`tr[data-usuario="${usuario}"]`);
}

test.describe.serial('Etapa 6.1 a 6.3', () => {
  test.beforeAll(() => {
    expect(ADMIN_USUARIO, 'rode via front/scripts/e2e.sh (prepara o admin)').not.toBe('');
    expect(ADMIN_SENHA).not.toBe('');
  });

  // 6.10: o admin (dono do primeiro acesso aqui) fica disponível para os testes finais.
  test.afterAll(() => {
    if (contas[ADMIN_USUARIO]) guardarConta('admin', conta(ADMIN_USUARIO));
  });

  test('6.1 rota protegida redireciona para o login e a API responde no mesmo origin', async ({
    page,
  }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('form', { name: 'Entrar' })).toBeVisible();
    const saude = await page.request.get('/api/saude');
    expect(saude.status()).toBe(200);
    expect((await page.request.get('/api/auth/sessao')).status()).toBe(401);
  });

  test('6.2 admin: primeiro acesso, código errado recusado, troca obrigatória antes de tudo', async ({
    page,
  }) => {
    await enviarSenha(page, ADMIN_USUARIO, ADMIN_SENHA);
    await expect(page.getByRole('heading', { name: 'Cadastre o autenticador' })).toBeVisible();
    const segredo = segredoDaUri(((await page.getByTestId('uri-mfa').textContent()) ?? '').trim());
    const autenticador = new Autenticador(segredo);
    await page.getByLabel('Código de 6 dígitos').fill(autenticador.errado());
    await page.getByRole('button', { name: 'Confirmar autenticador' }).click();
    await expect(page.getByRole('alert')).toContainText('Código inválido');
    await page.getByLabel('Código de 6 dígitos').fill(await autenticador.proximo());
    await page.getByRole('button', { name: 'Confirmar autenticador' }).click();
    await expect(page).toHaveURL(/\/trocar-senha$/);

    // Com troca pendente, nenhuma outra tela nem rota da API.
    await page.goto('/usuarios');
    await expect(page).toHaveURL(/\/trocar-senha$/);
    expect((await page.request.get('/api/usuarios')).status()).toBe(403);

    const senha = senhaNova();
    await page.getByLabel('Senha atual').fill(ADMIN_SENHA);
    await page.getByLabel('Nova senha', { exact: true }).fill(senha);
    await page.getByLabel('Confirme a nova senha').fill(senha);
    await page.getByRole('button', { name: 'Salvar nova senha' }).click();
    await expect(page.getByTestId('usuario-papel')).toHaveText('Administrador');
    await expect(page.getByTestId('estado-sessao')).toContainText('Sessão ativa');
    const menu = page.getByRole('navigation', { name: 'Menu principal' });
    await expect(menu.getByRole('link', { name: 'Usuários' })).toBeVisible();
    await expect(menu.getByRole('link', { name: 'Gabinetes' })).toBeVisible();
    contas[ADMIN_USUARIO] = { usuario: ADMIN_USUARIO, senha, autenticador };
    guardarConta('admin', conta(ADMIN_USUARIO));
  });

  test('6.3 admin cria gabinete e desembargador; senha temporária aparece uma única vez', async ({
    page,
  }) => {
    await entrar(page, conta(ADMIN_USUARIO));
    await page.getByRole('navigation', { name: 'Menu principal' }).getByRole('link', { name: 'Gabinetes' }).click();
    await page.getByLabel('Nome do gabinete').fill(GABINETE);
    await page.getByRole('button', { name: 'Criar gabinete' }).click();
    await expect(page.getByRole('status')).toContainText(`Gabinete ${GABINETE} criado`);
    await expect(page.getByRole('list', { name: 'Gabinetes cadastrados' })).toContainText(GABINETE);

    await page.getByLabel('Nome de usuário').fill(DESEMBARGADOR);
    await page.getByLabel('Gabinete', { exact: true }).selectOption({ label: GABINETE });
    await page.getByRole('button', { name: 'Criar desembargador' }).click();
    senhaTemporariaDesembargador = await lerSenhaTemporaria(page);
    await page.reload();
    await expect(page.getByText(senhaTemporariaDesembargador)).toHaveCount(0);

    await page.getByRole('navigation', { name: 'Menu principal' }).getByRole('link', { name: 'Usuários' }).click();
    const linhaDes = linha(page, DESEMBARGADOR);
    await expect(linhaDes).toContainText('Desembargador');
    await expect(linhaDes).toContainText(GABINETE);
    await expect(linhaDes.getByRole('button', { name: `Desativar ${DESEMBARGADOR}` })).toBeVisible();
    await expect(linhaDes.getByRole('button', { name: `Resetar senha de ${DESEMBARGADOR}` })).toBeVisible();
    await expect(linha(page, ADMIN_USUARIO).getByRole('button')).toHaveCount(0);
    await sair(page);
    expect((await page.request.get('/api/auth/sessao')).status()).toBe(401);
  });

  test('6.2/6.3 desembargador: primeiro acesso e gestão completa de assessor', async ({ page }) => {
    await primeiroAcesso(page, DESEMBARGADOR, senhaTemporariaDesembargador);
    await expect(page.getByTestId('usuario-papel')).toHaveText('Desembargador');
    const menu = page.getByRole('navigation', { name: 'Menu principal' });
    await expect(menu.getByRole('link', { name: 'Gabinetes' })).toHaveCount(0);
    await menu.getByRole('link', { name: 'Usuários' }).click();

    await expect(page.getByRole('heading', { name: 'Novo assessor' })).toBeVisible();
    await expect(page.getByLabel('Papel')).toHaveCount(0);
    await page.getByLabel('Nome de usuário').fill(ASSESSOR);
    await page.getByRole('button', { name: 'Criar assessor' }).click();
    const primeira = await lerSenhaTemporaria(page);

    const linhaAss = linha(page, ASSESSOR);
    await expect(linhaAss.getByTestId('situacao')).toHaveText(/Ativo · troca de senha pendente/);
    // 6.10: desativar pede confirmação; cancelar não muda nada.
    await linhaAss.getByRole('button', { name: `Desativar ${ASSESSOR}` }).click();
    const confirmacao = page.getByRole('dialog', { name: 'Desativar usuário?' });
    await expect(confirmacao).toBeVisible();
    await expect(confirmacao).toContainText(ASSESSOR);
    await expect(confirmacao.getByRole('button', { name: 'Cancelar' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(confirmacao).toBeHidden();
    await expect(linhaAss.getByTestId('situacao')).toHaveText(/^\s*Ativo/);
    await linhaAss.getByRole('button', { name: `Desativar ${ASSESSOR}` }).click();
    await confirmacao.getByRole('button', { name: 'Desativar' }).click();
    await expect(linhaAss.getByTestId('situacao')).toHaveText(/^\s*Inativo/);
    await linhaAss.getByRole('button', { name: `Reativar ${ASSESSOR}` }).click();
    await expect(linhaAss.getByTestId('situacao')).toHaveText(/^\s*Ativo/);
    await linhaAss.getByRole('button', { name: `Resetar senha de ${ASSESSOR}` }).click();
    senhaTemporariaAssessor = await lerSenhaTemporaria(page);
    expect(senhaTemporariaAssessor).not.toBe(primeira);
    await linhaAss.getByRole('button', { name: `Resetar autenticador de ${ASSESSOR}` }).click();
    await expect(page.getByRole('status')).toContainText('autenticador apagado');
    // Sobre si mesmo, nenhuma ação.
    await expect(linha(page, DESEMBARGADOR).getByRole('button')).toHaveCount(0);
  });

  test('6.3 matriz reconfirmada no servidor: desembargador recebe 403 nas ações do admin', async ({
    page,
  }) => {
    await entrar(page, conta(DESEMBARGADOR));
    await page.goto('/gabinetes');
    await expect(page.getByRole('alert')).toContainText('Só o administrador');
    await expect(page.getByRole('button', { name: 'Criar gabinete' })).toHaveCount(0);
    expect((await page.request.post('/api/gabinetes', { data: { nome: 'Gabinete pirata' } })).status()).toBe(403);
    expect((await page.request.get('/api/gabinetes')).status()).toBe(403);
    const desembargadorNovo = await page.request.post('/api/usuarios', {
      data: { nome_usuario: `des.pirata.${SUFIXO}`, papel: 'desembargador' },
    });
    expect(desembargadorNovo.status()).toBe(403);
    await sair(page);
  });

  test('6.2/6.3 assessor: primeiro acesso após reset; sem telas de gestão; servidor nega', async ({
    page,
  }) => {
    await primeiroAcesso(page, ASSESSOR, senhaTemporariaAssessor);
    await expect(page.getByTestId('usuario-papel')).toHaveText('Assessor');
    const menu = page.getByRole('navigation', { name: 'Menu principal' });
    await expect(menu.getByRole('link')).toHaveText(['Início', 'Processos']); // Processos: 6.4
    await page.goto('/usuarios');
    await expect(page.getByRole('alert')).toContainText('não dá acesso');
    expect((await page.request.get('/api/usuarios')).status()).toBe(403);
    const criar = await page.request.post('/api/usuarios', {
      data: { nome_usuario: `ass.pirata.${SUFIXO}`, papel: 'assessor' },
    });
    expect(criar.status()).toBe(403);
  });

  test('6.2 sessão expirada volta ao login com aviso', async ({ page, context }) => {
    await entrar(page, conta(DESEMBARGADOR));
    // Simula a expiração no servidor: o navegador deixa de ter uma sessão válida e a próxima
    // navegação descobre isso ao conferir a sessão.
    await context.clearCookies();
    await page.getByRole('navigation', { name: 'Menu principal' }).getByRole('link', { name: 'Usuários' }).click();
    await expect(page).toHaveURL(/\/login\?motivo=expirada$/);
    await expect(page.getByRole('status')).toContainText('Sessão encerrada ou expirada');
  });

  test('6.2 mensagens idênticas e bloqueio após 5 falhas sem revelar se o usuário existe', async ({
    page,
  }) => {
    const fantasma = `ninguem.${SUFIXO}`;
    await enviarSenha(page, ASSESSOR, 'senha-errada-de-proposito');
    const existente = await alerta(page);
    await enviarSenha(page, fantasma, 'senha-errada-de-proposito');
    const inexistente = await alerta(page);
    expect(existente).toBe(MENSAGEM_CREDENCIAIS);
    expect(inexistente).toBe(existente);

    for (let i = 0; i < 4; i++) {
      await enviarSenha(page, fantasma, 'senha-errada-de-proposito');
      await expect(page.getByRole('alert')).toHaveText(MENSAGEM_CREDENCIAIS);
      await enviarSenha(page, ASSESSOR, 'senha-errada-de-proposito');
      await expect(page.getByRole('alert')).toHaveText(MENSAGEM_CREDENCIAIS);
    }
    await enviarSenha(page, fantasma, 'senha-errada-de-proposito');
    const bloqueioInexistente = await alerta(page);
    // Nem a senha certa entra durante o bloqueio, e a mensagem é a mesma.
    await enviarSenha(page, ASSESSOR, conta(ASSESSOR).senha);
    const bloqueioExistente = await alerta(page);
    expect(bloqueioInexistente).toMatch(MENSAGEM_BLOQUEIO);
    expect(bloqueioExistente).toBe(bloqueioInexistente);
  });
});
